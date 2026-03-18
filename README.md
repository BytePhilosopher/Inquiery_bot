# Inquiry Bot

A Telegram bot for collecting and managing student inquiries, backed by Supabase and served through a FastAPI admin dashboard. Built for college/university support teams.

---

## Features

- **Telegram Bot** — Students submit inquiries in Amharic with structured info (name, gender, year, department, residence)
- **Admin Notifications** — Admin receives instant Telegram messages for every new inquiry
- **Ticket System** — Every inquiry gets a unique ticket ID; students can check status via `/status`
- **Admin Reply** — Admin replies to tickets directly from Telegram using `/reply <id> <message>`
- **Web Dashboard** — Password-protected admin panel to view, filter, search, and delete inquiries
- **CSV Export** — Export all inquiries as a spreadsheet
- **Supabase Database** — All data persisted in PostgreSQL via Supabase
- **Production Ready** — Rate limiting, security headers, structured logging, error pages

---

## Project Structure

```
Inquiery_bot/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, auth, dashboard routes
│   ├── bot.py           # Telegram bot handlers
│   ├── database.py      # Supabase DB functions
│   └── templates/
│       ├── dashboard.html
│       ├── login.html
│       └── error.html
├── supabase_schema.sql  # Run this once in Supabase SQL editor
├── requirements.txt
├── render.yaml          # Render deployment config
├── .env.example
└── .gitignore
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Bot framework | python-telegram-bot 21.3 |
| Web framework | FastAPI 0.115 + Uvicorn |
| Database | Supabase (PostgreSQL) |
| Templating | Jinja2 |
| Data export | Pandas |
| Deployment | Render |

---

## Setup

### 1. Prerequisites

- Python 3.11+
- A [Telegram bot token](https://t.me/BotFather) — create a bot via BotFather
- Your Telegram user ID — get it from [@userinfobot](https://t.me/userinfobot)
- A [Supabase](https://supabase.com) project

### 2. Clone the repo

```bash
git clone https://github.com/your-username/inquiry-bot.git
cd inquiry-bot
```

### 3. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_ID=your_telegram_user_id
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your_supabase_service_role_key
DASHBOARD_PASSWORD=your_secure_dashboard_password
WEBHOOK_URL=        # leave empty for local development
```

> **Where to find your Supabase key:**
> Supabase dashboard → your project → **Settings → API → service_role** key

### 5. Set up the database

Run the SQL in [supabase_schema.sql](supabase_schema.sql) inside your Supabase project:

Supabase dashboard → **SQL Editor** → paste and run:

```sql
create table if not exists inquiries (
  id          bigint generated always as identity primary key,
  user_id     bigint      not null,
  username    text,
  message     text        not null,
  status      text        not null default 'pending'
                          check (status in ('pending', 'resolved')),
  admin_reply text,
  created_at  timestamptz not null default now()
);
```

### 6. Run locally

```bash
uvicorn app.main:app --reload
```

- Dashboard → [http://localhost:8000](http://localhost:8000)
- Bot runs in polling mode automatically (no webhook needed locally)

---

## Bot Commands

### Student Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message with submission format guide |
| `/help` | Full guide on what to include in an inquiry |
| `/status` | View the last 5 submitted tickets and their status |

### Submission Format (Amharic)

Students should include these fields in their message:

```
ስም: አበበ ከበደ
ጾታ: ወንድ
ዓመት: 2015
ዲፓርትመንት: Computer Science
መኖሪያ: አዲስ አበባ
ጥያቄ: ...
```

### Admin Commands

| Command | Description |
|---------|-------------|
| `/reply <ticket_id> <message>` | Reply to a ticket and mark it resolved |
| `/pending` | List all unresolved tickets |

**Example:**
```
/reply 12 ጥቆማዎ ደርሷል፣ ቡድናችን በቅርቡ ይደርስዎታል።
```

---

## Dashboard

Access at `/` after signing in with your `DASHBOARD_PASSWORD`.

| Feature | Description |
|---------|-------------|
| Stats cards | Total / Pending / Resolved counts with resolution rate |
| Filter tabs | Filter by All / Pending / Resolved |
| Live search | Search by username or message content |
| Delete | Remove an inquiry with confirmation modal |
| Export CSV | Download all inquiries as a spreadsheet |
| Sign out | `/logout` clears the session |

---

## Deployment (Render)

### 1. Push to GitHub

```bash
git add .
git commit -m "initial deployment"
git push origin main
```

### 2. Create a Web Service on Render

- [render.com](https://render.com) → **New + → Web Service**
- Connect your GitHub repo
- Render auto-detects `render.yaml` — confirm settings

### 3. Set environment variables

In Render → your service → **Environment**, add:

| Key | Value |
|-----|-------|
| `BOT_TOKEN` | your Telegram bot token |
| `ADMIN_ID` | your Telegram user ID |
| `SUPABASE_URL` | your Supabase project URL |
| `SUPABASE_KEY` | your Supabase service_role key |
| `DASHBOARD_PASSWORD` | a strong password |
| `WEBHOOK_URL` | leave empty for now |
| `PYTHON_VERSION` | `3.11.0` |

### 4. Deploy

Click **Deploy Web Service** and wait for the build to complete.

### 5. Set WEBHOOK_URL

Once deployed, copy your Render URL (e.g. `https://inquiry-bot-xxxx.onrender.com`):

- Go to **Environment** → set `WEBHOOK_URL` = your Render URL
- Click **Save Changes** → Render redeploys automatically

### 6. Verify

- Visit your Render URL → login page should appear
- Send a message to your bot on Telegram → should reply and notify admin
- Visit `/health` → should return `{"status": "ok"}`

---

## Security

- Dashboard protected with session-based auth (7-day cookie)
- Login rate-limited to 5 attempts per 5 minutes per IP
- Security headers on all responses (`X-Frame-Options`, `X-Content-Type-Options`, etc.)
- Session cookie is `secure` + `httponly` in production (HTTPS only)
- Swagger/ReDoc disabled in production
- `.env` excluded from git via `.gitignore`

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram bot token from BotFather |
| `ADMIN_ID` | Yes | Your Telegram user ID (integer) |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase service_role key |
| `DASHBOARD_PASSWORD` | Yes | Password for the web dashboard |
| `WEBHOOK_URL` | No | Your deployed app URL (empty = polling mode) |
