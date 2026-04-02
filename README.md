# NESCO Prepaid Balance Bot

A Telegram bot that scrapes the NESCO customer portal to check prepaid electricity meter balance, recharge history, and monthly usage — without opening a browser.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [File Structure](#file-structure)
3. [How It Works — Full Flow](#how-it-works--full-flow)
4. [Module Reference](#module-reference)
5. [What Happens At Each Step](#what-happens-at-each-step)
6. [CSRF Protection Explained](#csrf-protection-explained)
7. [HTML Parsing Explained](#html-parsing-explained)
8. [Bot Commands](#bot-commands)
9. [Example Output](#example-output)
10. [Hosting](#hosting)
11. [Turning This Into a Public API](#turning-this-into-a-public-api)
12. [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Verify scraping works (no Telegram token needed)
python test_client.py

# 3. Create your config
cp .env.example .env
# Open .env and set TELEGRAM_BOT_TOKEN to your token from @BotFather

# 4. Run
python main.py
```

**Getting a bot token:** message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` → follow prompts → copy the token.

---

## File Structure

```
nesco_tg_bot/
│
├── main.py           Entry point. Loads .env, wires all pieces together, starts bot.
├── config.py         Reads environment variables into an immutable Config object.
├── bot.py            All Telegram command handlers live here (NescoBot class).
├── nesco_client.py   HTTP layer. Manages session, CSRF tokens, portal requests.
├── parser.py         HTML parser. Extracts data from portal pages using BeautifulSoup.
├── models.py         Data classes (CustomerInfo, RechargeRecord, etc.) + message formatting.
│
├── test_client.py    Dev utility. Runs a real scrape without needing a Telegram token.
│                     Use this when the portal changes its HTML and the parser breaks.
│
├── requirements.txt  Python package dependencies.
├── Procfile          One-line file telling Railway/Fly.io how to start the bot.
├── .env              Your local secrets. Never committed (listed in .gitignore).
├── .env.example      Template showing which env vars are needed.
└── .gitignore        Prevents .env and cache files from being committed to git.
```

---

## How It Works — Full Flow

This is the complete path from the moment a user sends a message to the moment they see a reply.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TELEGRAM SERVERS                                │
│                                                                         │
│   User sends:  /check 77900157                                          │
│         │                                                               │
│         │  Telegram delivers the update to our bot via long-polling     │
│         ▼                                                               │
└─────────────────────────────────────────────────────────────────────────┘
          │
          │  python-telegram-bot receives the Update object
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  bot.py — NescoBot.check()                                              │
│                                                                         │
│  1. Was a consumer number provided?  → if not, send usage hint          │
│  2. Is it all digits?               → if not, send error                │
│  3. Send "🔍 Fetching data..." loading message to user                  │
│  4. Call NescoClient.get_customer_info("77900157")                      │
└─────────────────────────────────────────────────────────────────────────┘
          │
          │  passes consumer number to HTTP layer
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  nesco_client.py — NescoClient._fetch()                                 │
│                                                                         │
│  Do we have a cached CSRF token?                                        │
│  ├── NO  → _refresh_csrf_token()                                        │
│  │         GET https://customer.nesco.gov.bd/pre/panel                  │
│  │         Parse HTML → extract hidden _token field                     │
│  │         Cache it in self._csrf_token                                 │
│  └── YES → reuse cached token                                           │
│                                                                         │
│  POST https://customer.nesco.gov.bd/pre/panel                           │
│       body: _token=<csrf>  cust_no=77900157  submit=রিচার্জ হিস্ট্রি   │
│                                                                         │
│  Response status?                                                        │
│  ├── 419 → token expired → refresh token → retry (max 2 times)         │
│  ├── redirect to /login → session invalid → refresh token → retry      │
│  └── 200 → pass HTML to parser                                          │
└─────────────────────────────────────────────────────────────────────────┘
          │
          │  raw HTML string
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  parser.py — NescoHTMLParser.parse_customer_page()                      │
│                                                                         │
│  BeautifulSoup loads the HTML into a navigable tree.                    │
│                                                                         │
│  For each data field (name, address, balance, meter no, etc.):          │
│  1. Find the <label> tag whose text contains the Bengali field name      │
│  2. Walk to the adjacent Bootstrap column div                           │
│  3. Read the value="" attribute from the <input> inside it              │
│                                                                         │
│  For the recharge history table:                                        │
│  1. Find the <table> whose header row contains "টোকেন"                 │
│  2. Parse each <tr> into a RechargeRecord                               │
│                                                                         │
│  Returns a CustomerInfo dataclass (or None if parsing fails)            │
└─────────────────────────────────────────────────────────────────────────┘
          │
          │  CustomerInfo object
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  models.py — CustomerInfo.format_telegram()                             │
│                                                                         │
│  Builds a Markdown-formatted string from the dataclass fields.          │
│  Chooses 🟢 or 🔴 based on whether balance < min_recharge.             │
│  Returns the final message string.                                      │
└─────────────────────────────────────────────────────────────────────────┘
          │
          │  formatted string
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  bot.py — NescoBot._run_lookup()                                        │
│                                                                         │
│  loading_msg.edit_text(formatted_string, parse_mode=MARKDOWN)           │
│  The loading "🔍 Fetching data..." message is replaced in-place.        │
└─────────────────────────────────────────────────────────────────────────┘
          │
          │  Telegram API call
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         TELEGRAM SERVERS                                │
│                                                                         │
│   User sees the formatted balance + customer info in the chat           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Module Reference

### `main.py` — Entry Point

```
load_dotenv()        reads .env file into environment variables
Config.from_env()    validates and packages the env vars into a Config object
NescoClient()        creates the HTTP session (not opened yet, lazy)
NescoBot(config, client)   injects both dependencies into the bot
bot.run()            builds the Telegram Application, starts long-polling (blocks forever)
client.close()       runs in the finally block — closes HTTP session on shutdown
```

**Why is `client.close()` in a `finally` block?**
If the bot crashes or you press Ctrl+C, Python still runs the `finally` block. This ensures the HTTP connection is cleanly closed rather than left dangling.

---

### `config.py` — Configuration

Reads environment variables once at startup and stores them in a frozen (immutable) dataclass. Frozen means no code can accidentally change `config.telegram_token` at runtime.

```python
@dataclass(frozen=True)
class Config:
    telegram_token: str   # required — bot crashes on startup if missing
    proxy_url: Optional[str] = None  # optional — for regions where Telegram is blocked
```

**Why not just use `os.getenv()` directly in bot.py?**
If the env var is missing, the error would appear deep inside the bot when it first tries to connect, making it hard to diagnose. Validating everything in `Config.from_env()` makes the bot fail immediately on startup with a clear message.

---

### `nesco_client.py` — HTTP Client

The only module that talks to the internet. Everything else works with Python objects.

| Method | What it does |
|--------|-------------|
| `get_customer_info(consumer_no)` | Public API — fetches balance and customer details |
| `get_monthly_usage(consumer_no)` | Public API — fetches 6-month usage table |
| `_fetch(consumer_no, submit, parse)` | Core — posts the form, handles retries, calls the parser |
| `_refresh_csrf_token()` | GET the portal page, extract and cache the hidden token |
| `_get_http()` | Returns the shared `httpx.Client`, creating it on first call (lazy init) |
| `close()` | Closes the HTTP session — called in `main.py`'s finally block |

**Why `httpx` and not `requests`?**
`httpx` has an almost identical API to `requests` but also supports async. If you later expose this as an async web API, you can switch to `httpx.AsyncClient` with minimal changes.

**Why synchronous, not async?**
`python-telegram-bot` runs its own `asyncio` event loop. Running an async HTTP client inside that same loop requires extra care. The sync `httpx.Client` keeps the HTTP code simple — it just blocks the thread while waiting for the portal to respond, which is fine because Telegram command handlers run in a thread pool.

---

### `parser.py` — HTML Parser

Knows nothing about Telegram or HTTP. Takes an HTML string, returns a data object.

The portal renders customer data as a two-column Bootstrap grid:

```html
<div class="col">
  <label>গ্রাহকের নাম</label>   ← Bengali for "Customer Name"
</div>
<div class="col">
  <input class="form-control" value="MD HABIBUR">
</div>
```

The parser finds each label by its Bengali text, then walks to the next sibling div to read the input value.

| Method | Purpose |
|--------|---------|
| `parse_customer_page(html)` | Main entry — coordinates all extraction, returns `CustomerInfo` |
| `parse_monthly_usage(html, consumer_no)` | Extracts the monthly usage table, returns `MonthlyUsageReport` |
| `extract_csrf_token(html)` | Finds `<input name="_token">` — used by the client before every POST |
| `_get_input_after_label(soup, label_text)` | Core field extraction — finds label → walks to input |
| `_parse_balance(soup)` | Balance needs special handling: value + timestamp both come from the same label |
| `_parse_recharge_table(soup)` | Finds the recharge history table by its "টোকেন" header |
| `_parse_recharge_row(row)` | Parses one `<tr>` into a `RechargeRecord` |
| `_parse_monthly_usage_row(row)` | Parses one `<tr>` into a `MonthlyUsage` |
| `_parse_float(text)` | Strips non-numeric characters, returns float (handles Bengali content) |
| `_parse_int(text)` | Same but returns int |
| `_parse_date(text)` | Tries multiple date formats used by the portal |

---

### `models.py` — Data Classes

Plain Python dataclasses. No HTTP, no Telegram, no HTML. Just data + formatting.

```
CustomerInfo
├── customer_name, address, mobile, office, feeder
├── consumer_no, meter_no, sanctioned_load, tariff
├── meter_type, meter_status, installation_date
├── min_recharge, balance, balance_updated_at
├── recharge_history: List[RechargeRecord]
│
├── format_telegram()   → full balance + info message
└── format_history()    → recharge transaction list

RechargeRecord
└── seq_no, token, meter_rate, demand_charge, pfc_charge,
    vat, arrear, rebate, energy_amount, recharge_amount,
    energy_kwh, payment_method, recharge_date, status

MonthlyUsage
└── year, month, total_recharge, rebate, energy_cost,
    meter_rent, demand_charge, pfc_charge, arrear,
    vat, total_deduction, end_balance, energy_kwh

MonthlyUsageReport
├── consumer_no
├── records: List[MonthlyUsage]
└── format_telegram()   → 6-month usage message
```

**Why put `format_telegram()` on the model instead of in bot.py?**
The model knows its own data best. If you later add an API or a web frontend, you don't duplicate the formatting logic — you add a new method like `format_json()` or `format_html()` to the same class.

---

### `bot.py` — Telegram Handlers

| Method | Triggered by |
|--------|-------------|
| `start()` | `/start` or `/help` |
| `check()` | `/check <number>` |
| `history()` | `/history <number>` |
| `usage()` | `/usage <number>` |
| `handle_message()` | Any plain text (not a command) |
| `_parse_consumer_no()` | Called by check/history/usage to validate args |
| `_run_lookup()` | Shared loading → fetch → reply flow used by all commands |
| `build()` | Wires all handlers to the Application |
| `run()` | Calls `build()` then starts long-polling |

**What is long-polling?**
Instead of waiting for Telegram to call your server (webhooks, which need a public URL), your bot repeatedly asks Telegram: "any new messages?" Telegram holds the connection open for up to 60 seconds, then responds with any pending updates. The bot immediately asks again. This means you can run the bot on any machine — even your laptop — without a public IP or domain.

---

## What Happens At Each Step

### Step 1 — Startup (`main.py`)

```
python main.py
    │
    ├── load_dotenv()          reads .env → sets os.environ
    ├── Config.from_env()      reads TELEGRAM_BOT_TOKEN → creates Config
    │                          crashes here with clear error if token is missing
    ├── NescoClient()          creates parser instance, sets _http=None (lazy)
    ├── NescoBot(config, client)
    └── bot.run()
            └── build()        registers all command handlers
            └── run_polling()  connects to Telegram, starts receiving updates
                               (this line blocks — the program lives here)
```

### Step 2 — First request (CSRF token fetch)

The very first time a user runs any command, there is no cached CSRF token:

```
_fetch() called
    │
    └── self._csrf_token is None
            │
            └── _refresh_csrf_token()
                    │
                    ├── GET https://customer.nesco.gov.bd/pre/panel
                    │       server returns full portal HTML page
                    │
                    └── extract_csrf_token(html)
                            │
                            └── soup.find('input', {'name': '_token'})
                                returns value="eyJ0eXAiOiJ..."
                                cached in self._csrf_token
```

### Step 3 — Portal POST

```
POST https://customer.nesco.gov.bd/pre/panel
    Headers:
        Content-Type: application/x-www-form-urlencoded
        Origin: https://customer.nesco.gov.bd
        Referer: https://customer.nesco.gov.bd/pre/panel
        User-Agent: Mozilla/5.0 ...
    Body:
        _token=eyJ0eXAiOiJ...
        cust_no=77900157
        submit=রিচার্জ হিস্ট্রি       ← Bengali text, exactly as the button says
```

The server validates the CSRF token, looks up the consumer number, and returns an HTML page with the customer data embedded in form inputs.

### Step 4 — Parsing

```
parse_customer_page(html)
    │
    ├── soup = BeautifulSoup(html, 'html.parser')
    │
    ├── For each field:
    │       _get_input_after_label(soup, "গ্রাহকের নাম")
    │           → find <label> containing "গ্রাহকের নাম"
    │           → find its parent col div
    │           → find next sibling div
    │           → find <input class="form-control"> inside it
    │           → return input["value"]  →  "MD HABIBUR"
    │
    ├── _parse_balance(soup)
    │       → same label-walking, but also extracts timestamp from <span>
    │
    └── _parse_recharge_table(soup)
            → find <table> whose header row contains "টোকেন"
            → for each <tr>: _parse_recharge_row(row)
                → cells[2] = token, cells[10] = amount, cells[12] = method ...
                → returns RechargeRecord
```

### Step 5 — Formatting and reply

```
CustomerInfo.format_telegram()
    │
    ├── balance < min_recharge?  → 🔴  else 🟢
    ├── Build multi-line Markdown string
    └── return string

loading_msg.edit_text(formatted_string, parse_mode=MARKDOWN)
    │
    └── Telegram replaces "🔍 Fetching data..." with the real result
        User sees the final message
```

---

## CSRF Protection Explained

CSRF (Cross-Site Request Forgery) is a web security mechanism. The NESCO portal is built with Laravel, which enforces it on every form POST.

**How it works:**

```
Browser visits page          →  Server generates a random secret token
                                 Embeds it in the HTML:
                                 <input name="_token" value="abc123">

Browser submits form         →  Sends _token=abc123 in the POST body
                                 Server checks: does this token match what I gave out?
                                 YES → process the request
                                 NO  → return HTTP 419 (token mismatch)
```

**Why tokens expire:**
The server stores tokens in the user's session, which has a timeout (usually 60-120 minutes). When the session expires, the token is gone from the server side, so the next POST gets a 419.

**How this bot handles it:**

```
First request           →  fetch token, cache it, make POST
Subsequent requests     →  reuse cached token (fast, no extra GET needed)
419 received            →  clear cache, fetch fresh token, retry (max 2 times)
Redirected to /login    →  same as 419 — session lost, refresh and retry
```

---

## HTML Parsing Explained

The portal renders data like this (simplified):

```html
<div class="row">
  <div class="col-md-3">
    <label class="col-form-label">গ্রাহকের নাম</label>
  </div>
  <div class="col-md-3">
    <input type="text" class="form-control" value="MD HABIBUR" readonly>
  </div>
  <div class="col-md-3">
    <label class="col-form-label">পিতা/স্বামীর নাম</label>
  </div>
  <div class="col-md-3">
    <input type="text" class="form-control" value="" readonly>
  </div>
</div>
```

BeautifulSoup builds a tree from this HTML. The parser navigates it like this:

```
Find all <label> tags
    For each label:
        Does its text contain "গ্রাহকের নাম"?
            YES → is the label itself a col div?
                    YES → label.find_next_sibling('div') → find input → return value
                    NO  → label.find_parent('div', class_='col-...')
                           → parent.find_next_sibling('div') → find input → return value
```

This two-pattern approach handles both ways the portal lays out its form fields.

---

## Bot Commands

| Command | Example | What it returns |
|---------|---------|-----------------|
| `/start` | `/start` | Welcome message and command list |
| `/help` | `/help` | Same as /start |
| `/check` | `/check 77900157` | Balance, customer info, last recharge |
| `/history` | `/history 77900157` | Last 5 recharge transactions |
| `/usage` | `/usage 77900157` | Last 6 months: recharged, used kWh, end balance |
| *(plain number)* | `77900157` | Same as /check |

---

## Example Output

**`/check 77900157`**
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

**`/usage 77900157`**
```
📊 Monthly Usage Report
Consumer: 77900157

📅 March 2026
   💰 Recharged: ৳500
   ⚡ Used: 23.81 kWh (৳0)
   📉 End Balance: ৳0.00

📅 February 2026
   💰 Recharged: ৳500
   ⚡ Used: 23.81 kWh (৳0)
   📉 End Balance: ৳0.00

─────────────────
📈 6-Month Summary:
   Total Recharged: ৳3,000
   Total Used: 142.9 kWh
```

---

## Hosting

This bot uses **long-polling** — it never needs an inbound connection. It reaches out to Telegram, so no public IP or domain is required.

| Platform | Free tier | Stays alive 24/7? | Outbound limits | Ease |
|----------|-----------|-------------------|-----------------|------|
| **Railway** | $5/month credit | Yes, ~500 hrs/month | None | Easiest |
| **Fly.io** | 3 VMs, no expiry | Yes, permanently | None | Easy |
| **Oracle Cloud** | 2 ARM VMs, permanent | Yes, permanently | None | Moderate (VM setup) |
| **Render** | Free tier | No — sleeps after 15 min idle | None | Easy but unusable |
| **PythonAnywhere** | Limited free | No — tasks expire | Outbound whitelist | Moderate |

### Railway (recommended to start)

```bash
git init && git add . && git commit -m "initial"
# Push to GitHub, then:
# railway.app → New Project → Deploy from GitHub
# Settings → Variables → TELEGRAM_BOT_TOKEN = your_token
```

### Fly.io (recommended for long term)

```bash
curl -L https://fly.io/install.sh | sh
fly auth login
fly launch --name nesco-tg-bot --region sin   # Singapore, closest to BD
fly secrets set TELEGRAM_BOT_TOKEN=your_token_here
fly deploy
```

---

## Turning This Into a Public API

Yes — and it requires less work than you might think. The scraping logic (`nesco_client.py`, `parser.py`, `models.py`) is already fully decoupled from Telegram. You add a second "frontend" that speaks HTTP instead of Telegram.

### What you would add

Install FastAPI:

```bash
pip install fastapi uvicorn
```

Create `api.py`:

```python
from fastapi import FastAPI, HTTPException
from nesco_client import NescoClient

app = FastAPI(title="NESCO Balance API")
client = NescoClient()

@app.get("/balance/{consumer_no}")
def get_balance(consumer_no: str):
    if not consumer_no.isdigit():
        raise HTTPException(status_code=400, detail="Consumer number must be numeric")
    info = client.get_customer_info(consumer_no)
    if not info:
        raise HTTPException(status_code=404, detail="Consumer not found")
    return {
        "consumer_no": info.consumer_no,
        "customer_name": info.customer_name,
        "balance": info.balance,
        "min_recharge": info.min_recharge,
        "balance_updated_at": info.balance_updated_at,
        "meter_status": info.meter_status,
    }

@app.get("/usage/{consumer_no}")
def get_usage(consumer_no: str):
    report = client.get_monthly_usage(consumer_no)
    if not report:
        raise HTTPException(status_code=404, detail="No usage data found")
    return {
        "consumer_no": report.consumer_no,
        "records": [
            {"year": r.year, "month": r.month,
             "total_recharge": r.total_recharge, "energy_kwh": r.energy_kwh,
             "end_balance": r.end_balance}
            for r in report.records
        ]
    }
```

Run it:

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Anyone can now call:

```
GET https://yourserver.com/balance/77900157
→ {"consumer_no": "77900157", "balance": 178.89, ...}
```

### The bot and API can run at the same time

`nesco_client.py` is just a class. You can share one instance between both:

```python
# main.py (modified)
client = NescoClient()
bot = NescoBot(config, client)    # Telegram frontend
api_app = build_api(client)       # HTTP frontend — same client, same session
```

### Things to add before making it public

| Concern | Solution |
|---------|---------|
| **Rate limiting** | Anyone can hammer your bot and get your IP banned by NESCO. Add `slowapi` (FastAPI rate limiter) — e.g. 10 requests/minute per IP |
| **API keys** | Don't leave it open. Require a key in the `Authorization` header. Issue keys manually or via a simple sign-up page |
| **Caching** | If 100 users check the same consumer number, you'd make 100 scrape requests. Cache results in memory for 5 minutes — `functools.lru_cache` or a dict with a timestamp |
| **HTTPS** | Required for any public API. Railway and Fly.io give you HTTPS automatically on their domains |
| **Terms of service** | NESCO's portal ToS likely prohibits automated access. Understand the legal risk before publishing a public API built on scraped data |

### Deployment for the API version

The API needs a web port exposed, so update `Procfile`:

```
web: uvicorn api:app --host 0.0.0.0 --port $PORT
worker: python main.py
```

Railway and Fly.io both support running multiple processes or separate services.

---

## Troubleshooting

**`ValueError: TELEGRAM_BOT_TOKEN environment variable is required`**
You haven't created `.env` or the token is missing. Run `cp .env.example .env` and add your token.

**`"Could not extract CSRF token"`**
The portal is temporarily down or returned an unexpected page. Wait a few minutes and retry.

**`"No data found for consumer: ..."`**
The consumer number is wrong or it's not a NESCO prepaid account.
Verify manually at [customer.nesco.gov.bd/pre/panel](https://customer.nesco.gov.bd/pre/panel).

**Parser returns `N/A` for most fields**
The portal changed its HTML structure. Run:
```bash
python test_client.py --debug
```
This saves the raw HTML to `debug_response.html`. Open it in a browser, inspect the element for any field, and update `parser.py` to match the new structure.

**Bot stops responding after hours/days**
The long-polling connection dropped. On Railway/Fly.io the process restarts automatically. Locally, restart `python main.py`.

---

## License

MIT
