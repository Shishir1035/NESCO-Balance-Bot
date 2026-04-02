# NESCO Prepaid Balance Bot

A Telegram bot that scrapes the [NESCO customer portal](https://customer.nesco.gov.bd/pre/panel) to check prepaid electricity meter balance, recharge history, and monthly usage — without visiting the website.

## Features

- Check current balance with low-balance warning
- View last 5 recharge transactions
- View 6-month usage report
- Quick lookup: just send the consumer number as a plain message

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Test scraping without a Telegram token (optional sanity check)
python test_client.py

# 3. Copy the env template and add your bot token
cp .env.example .env
# Edit .env and set TELEGRAM_BOT_TOKEN

# 4. Run
python main.py
```

### Getting a Telegram Bot Token

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, follow the prompts, and copy the token
3. Paste it into your `.env` file as `TELEGRAM_BOT_TOKEN=...`

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` or `/help` | Welcome message with usage guide |
| `/check 77900157` | Balance and full customer info |
| `/history 77900157` | Last 5 recharge transactions |
| `/usage 77900157` | Monthly usage report (last 6 months) |
| `77900157` | Quick check — just send the number |

## Example Output

```
🔋 NESCO Prepaid Balance

👤 MD MAHABUL HAQUE
📍 DURGAPUR ROAD CALAKPUR

┌─────────────────────
│ 🔌 Meter: 31011041579
│ 📊 Consumer: 77900157
│ ⚡ Load: 2.0 kW (LT-A)
│ 📶 Status: Active
└─────────────────────

🟢 Balance: ৳178.89
🕐 Updated: 31 March 2026 12:00:00 AM

📅 Last Recharge:
   ৳500 via BKASH
   03-Feb-2026 10:53 AM
```

---

## Architecture

```
Telegram User
     │  sends /check 77900157
     ▼
NescoBot  (bot.py)
  Handles commands, validates input, sends replies
     │
     ▼
NescoClient  (nesco_client.py)
  Manages HTTP session and CSRF tokens
  GET /pre/panel → extract CSRF token
  POST /pre/panel with consumer number → get HTML
     │
     ▼
NescoHTMLParser  (parser.py)
  BeautifulSoup parses the HTML
  Finds labels in Bengali, extracts adjacent input values
  Parses recharge and usage tables
     │
     ▼
Data Models  (models.py)
  CustomerInfo, RechargeRecord, MonthlyUsage
  Each model has a format_telegram() method for display
```

### File Structure

```
nesco_tg_bot/
├── main.py          # Entry point: loads .env, wires dependencies, starts bot
├── bot.py           # Telegram command handlers (NescoBot class)
├── nesco_client.py  # HTTP client: session management, CSRF handling
├── parser.py        # HTML parser: BeautifulSoup extraction logic
├── models.py        # Data classes + Telegram message formatting
├── config.py        # Reads environment variables into a Config dataclass
├── test_client.py   # Standalone test (no Telegram token needed)
├── requirements.txt
├── Procfile         # For Railway / Fly.io deployment
├── .env.example     # Template — copy to .env and fill in your token
└── .gitignore       # Keeps .env and debug files out of git
```

### Key Design Decisions

| Decision | Why |
|----------|-----|
| **Dependency injection** | `NescoBot` receives `Config` and `NescoClient` in its constructor, making it easy to swap implementations or test without a real HTTP client |
| **CSRF token caching** | The portal uses Laravel CSRF protection. We fetch the token once and reuse it; on a 419 response the client auto-refreshes (max 2 retries to avoid infinite loops) |
| **Synchronous httpx** | `python-telegram-bot` handles its own async event loop. Using sync `httpx.Client` avoids running a nested event loop and keeps the HTTP code simple |
| **Bengali form fields** | The portal submit buttons contain Bengali text (`রিচার্জ হিস্ট্রি`, `মাসিক ব্যবহার`) — these are sent as-is in the POST form data |

### How CSRF Works Here

Web forms include a hidden `_token` field to prevent cross-site request forgery. The NESCO portal (built on Laravel) requires this token on every POST. The flow is:

1. `GET /pre/panel` → server returns an HTML page with `<input name="_token" value="abc123...">`
2. We extract that token with BeautifulSoup
3. Every POST includes `_token=abc123...` in the form body
4. If the token expires (HTTP 419), we fetch a fresh one and retry

---

## Hosting for Free

This bot runs as a **long-polling worker** (it keeps one persistent connection to Telegram's servers). It does not need a public URL or web server.

### Option 1: Railway (Recommended for beginners)

Railway gives $5/month free credit — more than enough for a lightweight bot.

1. Push your code to a GitHub repo (make sure `.env` is in `.gitignore`)
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add environment variables in the Railway dashboard (Settings → Variables):
   - `TELEGRAM_BOT_TOKEN` = your token
4. Railway reads `Procfile` and runs `python main.py` automatically
5. Done — the bot stays running 24/7

### Option 2: Fly.io (Free tier, more control)

Fly.io has a generous always-free tier (3 shared VMs).

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login and create the app
fly auth login
fly launch          # follow prompts, choose a region close to Bangladesh

# Set your bot token as a secret (never stored in files)
fly secrets set TELEGRAM_BOT_TOKEN=your_token_here

# Deploy
fly deploy
```

Fly.io uses `Procfile` automatically, or you can add a `fly.toml` for more control.

### Option 3: Oracle Cloud Always Free

Oracle Cloud offers 2 ARM VMs free forever (no expiry, no credit card charges after signup).

1. Sign up at cloud.oracle.com → create an Ampere ARM instance (Always Free)
2. SSH in, install Python, clone your repo
3. Run with `nohup python main.py &` or set up a systemd service

This is the most reliable free option long-term, but requires more setup.

### Option 4: Render (easiest, but has a catch)

Render's free tier **spins down after 15 minutes of inactivity**. Since a polling bot has no incoming HTTP traffic, it will sleep immediately — not suitable without a paid plan.

### What NOT to use

- **GitHub Actions** — designed for CI/CD jobs, not persistent processes
- **Vercel / Netlify** — serverless platforms for web apps, not background workers
- **Render free tier** — spins down as described above

---

## Troubleshooting

**"Could not extract CSRF token"**
The portal may be temporarily down. Wait a few minutes and try again.

**"No data found for consumer: ..."**
The consumer number is wrong or not a NESCO prepaid customer.
Verify it at [customer.nesco.gov.bd/pre/panel](https://customer.nesco.gov.bd/pre/panel).

**Parser returns mostly N/A values**
The portal HTML structure may have changed. Run `python test_client.py --debug` to save the raw HTML, then inspect it to find what changed in `parser.py`.

**Bot stops responding after a while**
The Telegram polling connection dropped. On Railway/Fly.io this restarts automatically. Locally, just restart `python main.py`.

---

## License

MIT
