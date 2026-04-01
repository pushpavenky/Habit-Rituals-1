from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sqlite3, os, json, requests
from datetime import datetime, date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH     = os.environ.get("DB_PATH", "bodyritual.db")
RESEND_KEY  = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM  = os.environ.get("EMAIL_FROM", "")        # e.g. habits@yourdomain.com
EMAIL_TO    = os.environ.get("EMAIL_TO", "")
TRACKER_URL = os.environ.get("TRACKER_URL", "https://your-tracker-link")

HABITS = ["workout", "water", "stretch"]

# ── DB SETUP ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS days (
            date TEXT PRIMARY KEY,
            habits TEXT NOT NULL DEFAULT '{}',
            mood INTEGER DEFAULT -1,
            notes TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ── MODELS ────────────────────────────────────────────────────────────────────

class DayUpdate(BaseModel):
    habits: dict
    mood: Optional[int] = -1
    notes: Optional[str] = ""

# ── HELPERS ───────────────────────────────────────────────────────────────────

def today_ist():
    return datetime.now(pytz.timezone("Asia/Kolkata")).date().isoformat()

def get_day_row(date_key: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM days WHERE date = ?", (date_key,)).fetchone()
    conn.close()
    return row

def get_streak():
    conn = get_db()
    rows = conn.execute("SELECT date, habits FROM days ORDER BY date DESC LIMIT 60").fetchall()
    conn.close()
    today = today_ist()
    streak = 0
    for i in range(60):
        d = (date.fromisoformat(today) - timedelta(days=i)).isoformat()
        row = next((r for r in rows if r["date"] == d), None)
        habits = json.loads(row["habits"]) if row else {}
        done = sum(1 for h in HABITS if habits.get(h))
        if d == today and done == 0 and i == 0:
            continue
        if done >= 2:
            streak += 1
        elif i > 0:
            break
    return streak

def get_last7_dots():
    today = today_ist()
    conn = get_db()
    rows = conn.execute("SELECT date, habits FROM days WHERE date >= ?",
                        ((date.fromisoformat(today) - timedelta(days=6)).isoformat(),)).fetchall()
    conn.close()
    row_map = {r["date"]: json.loads(r["habits"]) for r in rows}
    dots = []
    for i in range(6, -1, -1):
        d = (date.fromisoformat(today) - timedelta(days=i)).isoformat()
        habits = row_map.get(d, {})
        done = sum(1 for h in HABITS if habits.get(h))
        if done == 3:   dots.append("🟢")
        elif done >= 1: dots.append("🟡")
        else:           dots.append("⬜")
    return dots

# ── API ROUTES ────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "service": "Body Ritual"}

@app.get("/day/{date_key}")
def get_day(date_key: str):
    row = get_day_row(date_key)
    if not row:
        return {"date": date_key, "habits": {}, "mood": -1, "notes": ""}
    return {
        "date": row["date"],
        "habits": json.loads(row["habits"]),
        "mood": row["mood"],
        "notes": row["notes"],
    }

@app.post("/day/{date_key}")
def save_day(date_key: str, body: DayUpdate):
    conn = get_db()
    conn.execute("""
        INSERT INTO days (date, habits, mood, notes)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            habits = excluded.habits,
            mood   = excluded.mood,
            notes  = excluded.notes
    """, (date_key, json.dumps(body.habits), body.mood, body.notes))
    conn.commit()
    conn.close()
    return {"saved": True}

@app.get("/stats")
def get_stats():
    streak     = get_streak()
    dots       = get_last7_dots()
    today      = today_ist()
    row        = get_day_row(today)
    habits     = json.loads(row["habits"]) if row else {}
    done_today = sum(1 for h in HABITS if habits.get(h))
    return {
        "streak":     streak,
        "last7":      dots,
        "done_today": done_today,
        "total":      len(HABITS),
    }

@app.get("/history")
def get_history():
    conn = get_db()
    rows = conn.execute("SELECT * FROM days ORDER BY date DESC LIMIT 30").fetchall()
    conn.close()
    return [{"date": r["date"], "habits": json.loads(r["habits"]),
             "mood": r["mood"], "notes": r["notes"]} for r in rows]

# ── EMAIL DIGEST (via Resend HTTP API — works on Railway) ─────────────────────

def send_email_digest():
    if not RESEND_KEY or not EMAIL_FROM or not EMAIL_TO:
        print("Email not configured (RESEND_API_KEY / EMAIL_FROM / EMAIL_TO), skipping digest")
        return

    streak     = get_streak()
    dots       = get_last7_dots()
    today      = today_ist()
    row        = get_day_row(today)
    habits     = json.loads(row["habits"]) if row else {}
    done_today = sum(1 for h in HABITS if habits.get(h))

    habit_lines = {
        "workout": ("🏃", "Move / Workout"),
        "water":   ("🥤", "Drink 2L water"),
        "stretch": ("🫧", "Wash feet before bed"),
    }

    streak_line = (
        f"🔥 {streak}-day streak" if streak > 1
        else ("🌱 Start your streak tonight" if streak == 0
              else "🌱 Day 1 — begin tonight")
    )
    done_line = "🎯 All three done today — log it." if done_today == 3 else "👉 Time to log before bed."

    # HTML email (identical to original)
    rows_html = ""
    for h, (icon, name) in habit_lines.items():
        done  = habits.get(h)
        tick  = "✅" if done else "⬜"
        style = "text-decoration:line-through;color:#888;" if done else "color:#1a1a1a;"
        rows_html += f"""
          <tr>
            <td style="padding:10px 4px;font-size:18px;width:30px;">{tick}</td>
            <td style="padding:10px 4px;font-size:16px;width:28px;">{icon}</td>
            <td style="padding:10px 4px;font-size:15px;{style}">{name}</td>
          </tr>"""

    dot_colors = {"🟢": "#1D9E75", "🟡": "#EF9F27", "⬜": "#ddd8ce"}
    dots_html  = "".join(
        f'<span style="display:inline-block;width:13px;height:13px;border-radius:3px;'
        f'background:{dot_colors.get(d,"#ddd8ce")};margin:0 2px;vertical-align:middle;"></span>'
        for d in dots
    )

    html_body = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:20px;background:#eee;font-family:'Helvetica Neue',Helvetica,sans-serif;">
  <div style="max-width:400px;margin:0 auto;background:#f5f0e8;border-radius:16px;overflow:hidden;">
    <div style="background:#0a2e1e;padding:28px 24px 22px;">
      <div style="font-size:10px;letter-spacing:0.14em;color:#5DCAA5;text-transform:uppercase;margin-bottom:6px;">Body Ritual</div>
      <div style="font-size:22px;font-weight:700;color:#fff;margin-bottom:16px;">9 PM Check-in</div>
      <div style="margin-bottom:6px;">{dots_html}</div>
      <div style="font-size:11px;color:rgba(255,255,255,0.35);margin-top:4px;">last 7 days &nbsp;🟢 full &nbsp;🟡 partial &nbsp;⬜ none</div>
    </div>
    <div style="padding:20px 24px 28px;">
      <table style="width:100%;border-collapse:collapse;">{rows_html}</table>
      <div style="margin-top:18px;padding:16px;background:#fff;border-radius:12px;">
        <div style="font-size:15px;font-weight:600;color:#1a1a1a;margin-bottom:4px;">{streak_line}</div>
        <div style="font-size:14px;color:#555;">{done_line}</div>
      </div>
      <div style="margin-top:18px;text-align:center;">
        <a href="{TRACKER_URL}"
           style="display:inline-block;background:#1D9E75;color:#fff;text-decoration:none;
                  padding:13px 32px;border-radius:10px;font-size:15px;font-weight:600;">
          Open Tracker →
        </a>
      </div>
    </div>
  </div>
</body></html>"""

    subject_prefix = "✅ All done!" if done_today == 3 else "👉 Log before bed"
    subject = f"{subject_prefix} — Body Ritual {today}"

    # ── RESEND HTTP API (replaces smtplib) ────────────────────────────────────
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": EMAIL_FROM,
                "to": [EMAIL_TO],
                "subject": subject,
                "html": html_body,
            },
            timeout=10,
        )
        if resp.status_code == 200 or resp.status_code == 201:
            print(f"Digest emailed via Resend at {datetime.now()}")
        else:
            print(f"Resend error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"Email error: {e}")

# ── SCHEDULER ─────────────────────────────────────────────────────────────────

scheduler = BackgroundScheduler(timezone=pytz.timezone("Asia/Kolkata"))
scheduler.add_job(
    send_email_digest,
    CronTrigger(hour=21, minute=0, timezone=pytz.timezone("Asia/Kolkata"))
)
scheduler.start()

@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()
