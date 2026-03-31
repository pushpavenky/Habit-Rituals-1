# Body Ritual — Deploy Guide

## Stack
- **FastAPI** on Railway (free tier) — habit data in SQLite
- **Gmail SMTP** — free daily digest email at 9 PM IST
- **body-ritual.html** — your tracker, hosted on tiiny.host

---

## Step 1 — Get a Gmail App Password (3 min)

Regular Gmail passwords won't work — you need an App Password:

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** if not already on
3. Search "App passwords" → create one → name it "Body Ritual"
4. Copy the **16-character password** (shown once)

That's it. No sign-ups, no billing, completely free forever.

---

## Step 2 — Deploy to Railway (5 min)

**Option A — GitHub (recommended):**
1. Push this folder to a new GitHub repo
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select the repo → Railway auto-detects Python and deploys

**Option B — Railway CLI:**
```bash
npm install -g @railway/cli
railway login
cd bodyritual
railway init
railway up
```

Railway gives you a URL like `https://bodyritual-production.up.railway.app`

---

## Step 3 — Set environment variables in Railway

Go to your Railway project → **Variables** tab → add these:

| Variable | Value |
|---|---|
| `GMAIL_USER` | your.email@gmail.com |
| `GMAIL_APP_PASS` | the 16-char app password from Step 1 |
| `EMAIL_TO` | where digest lands (can be same Gmail or any email) |
| `TRACKER_URL` | your tiiny.host link |
| `DB_PATH` | `/data/bodyritual.db` |

**Add a Volume** for persistent storage:
- Railway project → **Volumes** → Add Volume → mount at `/data`

---

## Step 4 — Update body-ritual.html

Open `body-ritual.html`, find at the top of the `<script>` block:

```js
const API = "https://YOUR-RAILWAY-APP.up.railway.app";
```

Replace with your actual Railway URL. Re-upload to tiiny.host.

---

## Step 5 — Verify

Visit your Railway URL:
```
https://your-app.up.railway.app/
→ {"status": "ok", "service": "Body Ritual"}

https://your-app.up.railway.app/stats
→ {"streak": 0, "last7": [...], "done_today": 0, "total": 3}
```

The digest fires at 9:00 PM IST every day automatically.

---

## What the email looks like

**Subject:** `👉 Log before bed — Body Ritual 2026-03-31`
(or `✅ All done! — Body Ritual 2026-03-31` when you've checked everything)

The email has:
- A dark green header with 7-day dot heatmap
- Live checklist showing what's ticked vs pending
- Streak count
- "Open Tracker →" button linking to your tracker

---

## Cost breakdown

| Service | Cost |
|---|---|
| Railway (hobby plan) | Free (500hr/month) |
| Gmail SMTP | Free forever |
| tiiny.host | Free |
| **Total** | **$0** |

---

## File structure

```
bodyritual/
├── app/
│   └── main.py        # FastAPI + SQLite + Gmail scheduler
├── requirements.txt
├── Procfile
├── railway.toml
├── body-ritual.html   # Tracker (update API url before uploading)
└── README.md
```
