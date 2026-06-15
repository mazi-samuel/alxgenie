# 📚 Telegram Personal Assistant Bot

A Python bot that connects your Google Sheets to your Telegram channel — auto-posting weekly **random Top 10 graduate spotlights** per course, plus letting you pre-schedule custom posts to drop at any time.

---

## Features

| Feature | Details |
|---|---|
| 📊 Google Sheets sync | Reads graduates from your spreadsheet (multi-tab or single-sheet layouts) |
| 🏆 Weekly Top 10 | Auto-posts a random Top 10 spotlight for every course on a set day/time |
| 📅 Feed Scheduler | Pre-write posts, assign a date & time, bot auto-publishes them |
| 📋 Browse Graduates | `/graduates`, `/stats`, `/courses` commands |
| 🔐 Admin-only | Scheduling and manual post commands are locked to your user ID |

---

## Project Structure

```
telegram bot/
├── bot.py              ← Main bot (run this)
├── sheets.py           ← Google Sheets integration
├── database.py         ← SQLite for scheduled feeds
├── formatters.py       ← Message formatting
├── config.py           ← Configuration loader
├── requirements.txt    ← Python dependencies
├── .env                ← Your secrets (create from .env.example)
├── .env.example        ← Template
├── credentials.json    ← Google Service Account key (you create this)
└── feeds.db            ← Auto-created SQLite database
```

---

## Setup Guide

### Step 1 — Create your Telegram Bot

1. Open Telegram and message **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy your **Bot Token** — you'll need it for `.env`
4. Send `/mybots` → select your bot → **Bot Settings** → **Allow Groups** → enable
5. Add the bot to your channel as an **Administrator** (with "Post Messages" permission)

**Get your User ID:**
- Message **@userinfobot** → it replies with your numeric user ID

**Get your Channel ID:**
- For public channels: use `@yourchannel`
- For private channels: forward a message from the channel to **@userinfobot** to get its numeric ID (starts with `-100`)

---

### Step 2 — Set Up Google Sheets Access

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable these two APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. Go to **IAM & Admin → Service Accounts** → Create a service account
5. Give it any name (e.g. `telegram-bot`)
6. Click the service account → **Keys** tab → **Add Key** → **Create new key** → **JSON**
7. Download the JSON file and rename it to **`credentials.json`**
8. Place `credentials.json` in the same folder as `bot.py`
9. **Share your Google Sheet** with the service account email (found in credentials.json as `"client_email"`)
   - Open the spreadsheet → Share → paste the email → give **Viewer** access

---

### Step 3 — Spreadsheet Format

The bot supports two layouts:

**Option A — Separate tabs per course (recommended)**

Each tab/sheet = one course. Each tab should have these columns:

| Name | Completion Date | Week |
|------|----------------|------|
| John Doe | 2026-06-01 | Week 1 |
| Jane Smith | 2026-06-02 | Week 1 |

> Tab names become your course names. Tabs named "Summary", "Overview", or "Index" are skipped.

**Option B — Single sheet with a Course column**

| Name | Course | Completion Date | Week |
|------|--------|----------------|------|
| John Doe | Data Science | 2026-06-01 | Week 1 |

> Set `SHEET_MODE=column` in `.env`

---

### Step 4 — Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
TELEGRAM_BOT_TOKEN=1234567890:AAFxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHANNEL_ID=@yourchannel
ADMIN_USER_ID=987654321
GOOGLE_SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms

SHEET_MODE=tabs
COL_NAME=Name
COL_DATE=Completion Date
COL_WEEK=Week

WEEKLY_POST_DAY=mon
WEEKLY_POST_TIME=09:00
TIMEZONE=Africa/Lagos
```

---

### Step 5 — Install & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python bot.py
```

The bot will start and you'll see log output. Keep this terminal window open (or use a process manager for always-on hosting).

---

## Bot Commands

### Public Commands
| Command | Description |
|---|---|
| `/start` | Show help and command list |
| `/courses` | List all courses from the spreadsheet |
| `/stats` | Show total graduates per course |
| `/graduates [course]` | Browse graduates for a course |
| `/top10 [course]` | Show a random Top 10 spotlight |

### Admin-Only Commands
| Command | Description |
|---|---|
| `/postweekly` | Immediately post weekly Top 10 for all courses |
| `/schedule` | Launch the scheduling wizard to pre-schedule a post |
| `/listfeeds` | View all upcoming scheduled posts |
| `/deletefeed [id]` | Cancel a scheduled post |

---

## Scheduling Posts

Use `/schedule` to open the 3-step wizard:

1. **Type your message** — exactly as you want it to appear in the channel
2. **Enter the date** — `DD/MM/YYYY` format (e.g. `20/06/2026`)
3. **Enter the time** — `HH:MM` 24-hour (e.g. `09:00`)
4. **Confirm** — bot saves it and auto-posts when the time arrives

The bot checks every 60 seconds for due posts.

---

## Always-On Hosting (Optional)

To keep the bot running 24/7:

### Windows (using NSSM)
```bash
nssm install TelegramBot "python" "C:\path\to\bot.py"
nssm start TelegramBot
```

### Linux/Mac (using systemd or screen)
```bash
screen -S telegrambot
python bot.py
# Ctrl+A then D to detach
```

Or deploy to a free cloud server (Railway, Render, VPS).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing required environment variable` | Check your `.env` file has all values filled in |
| `WorksheetNotFound` | Check the course name exactly matches the tab name |
| `Forbidden: bot is not a member` | Add the bot as admin to your channel |
| `credentials.json not found` | Place the Google service account JSON in the bot folder |
| Column not found warning | Check `COL_NAME`, `COL_DATE`, `COL_WEEK` in `.env` match your spreadsheet headers exactly |

---

## Column Name Customisation

If your spreadsheet uses different column names (e.g. "Full Name" instead of "Name"), just update `.env`:

```env
COL_NAME=Full Name
COL_DATE=Date Completed
COL_WEEK=Cohort Week
```
