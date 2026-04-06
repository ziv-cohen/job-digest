# Job Digest Pipeline

A lightweight, automated job search pipeline that queries multiple job boards daily, deduplicates and scores results against your personal criteria, and delivers a ranked digest via Telegram (or email).

Built in Python with no heavy frameworks — designed to be easy to understand, fork, and extend.

## What it does

```
Sources → Normalize → Deduplicate → Score → Filter → Sort → Deliver
```

Every morning (or on demand):

1. **Fetches** jobs from multiple sources (JSearch/Google Jobs, Adzuna, Remotive, StartupJobs.cz)
2. **Deduplicates** using fuzzy title+company matching across sources
3. **Scores** each job on a 100-point scale based on your criteria (role, location, company type, seniority, freshness)
4. **Filters** out jobs below your minimum score and older than N days
5. **Delivers** a ranked digest to Telegram or email

## Example output (Telegram)

```
#1  [72.0 pts]  Engineering Director — Platform
    Stripe · London (Remote, EMEA)
    GBP 130,000 – 160,000
    Product company · Director · Growing company
    Posted: 01 Apr 2026 · adzuna
```

## Project structure

```
job-digest/
├── main.py                  # Orchestrator — runs the full pipeline
├── models.py                # Job dataclass (shared schema)
├── config.yaml              # All config + defaults (committed, no secrets)
├── config.local.yaml        # Your secrets and overrides (gitignored)
├── config_loader.py         # Merges base config + local overrides + env vars
│
├── sources/                 # One file per job source
│   ├── jsearch.py           # Google Jobs via RapidAPI (broadest coverage)
│   ├── adzuna.py            # Adzuna European API (GB, DE, FR, NL, AT, PL)
│   ├── remotive.py          # Remotive.io (remote jobs, free API)
│   ├── startupjobs.py       # StartupJobs.cz (Czech startup scene)
│   └── linkedin_email.py    # LinkedIn alerts via Gmail IMAP (optional)
│
├── pipeline/
│   ├── deduplicator.py      # Fuzzy deduplication (82% similarity threshold)
│   └── scorer.py            # 100-point scoring engine
│
├── output/
│   ├── telegram_digest.py   # Sends ranked digest via Telegram Bot API
│   └── email_digest.py      # Sends ranked digest via SMTP (fallback)
│
├── tests/                   # Full unit test suite (212 tests, offline)
│   ├── conftest.py
│   ├── sources/
│   └── ...
│
├── Dockerfile               # For containerised deployment
└── railway.toml             # Railway.app cron config
```

## Scoring system

Each job is scored out of 100 (+ up to 8 bonus points). All weights are configurable in `config.yaml`.

| Dimension | Max pts | Key signals |
|-----------|---------|-------------|
| **Title match** | 30 | "Engineering Director", "Sr. EM", "EM", "Founding CTO" |
| **Location fit** | 25 | EMEA remote = Prague on-site (25), Czech remote (20), commute tiers |
| **Company type** | 20 | Product company (20), outsourcing (15), consulting (8) |
| **Seniority** | 15 | Director (15), Senior Manager (12), Manager (8) |
| **Freshness** | 10 | Today (10), yesterday (7), 2-3 days (4), 4-7 days (2) |
| **Bonus** | +8 | Growth signals, salary disclosed, freelancer-friendly |

Jobs older than `max_age_days` (default: 7) are hard-filtered before scoring.

## Getting started

### 1. Clone and install

```bash
git clone https://github.com/your-username/job-digest.git
cd job-digest
pip install -r requirements.txt
```

### 2. Get API keys

| Source | Key needed | Free tier |
|--------|-----------|-----------|
| **JSearch** (Google Jobs) | RapidAPI key | 200 req/month free — [sign up](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) |
| **Adzuna** | App ID + App Key | Free — [sign up](https://developer.adzuna.com/) |
| **Remotive** | None | Public API |
| **StartupJobs.cz** | None | Public scraping |

### 3. Create your local config

Copy `config.yaml` to `config.local.yaml` and fill in your values. The local file is gitignored and never committed.

```bash
cp config.yaml config.local.yaml
```

Minimal `config.local.yaml`:

```yaml
api_keys:
  jsearch_rapidapi_key: "your-key-here"
  adzuna_app_id: "your-app-id"
  adzuna_app_key: "your-app-key"

telegram:
  bot_token: "your-bot-token"   # from @BotFather on Telegram
  chat_id: "your-chat-id"       # send any message to your bot, then GET /getUpdates
```

**To get your Telegram bot:**
1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token
2. Send any message to your new bot
3. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` — copy `chat.id` from the response

Alternatively, configure `email` in `config.local.yaml` to use SMTP delivery instead.

### 4. Customize for yourself

Edit `config.yaml` (or override in `config.local.yaml`) to match your search criteria:

```yaml
search:
  role_titles:
    - "engineering director"
    - "VP engineering"
    - "your role here"

  locations:
    primary_city: "Your City"
    country: "Your Country"
    region: "EMEA"   # or "Americas", "APAC", etc.
```

Adjust scoring weights, location tiers, and bonus signals in the `scoring:` section to reflect what matters to you.

### 5. Run it

```bash
# Fetch, score, print results — no message sent (recommended for first run)
python main.py --dry-run

# Just fetch — print raw counts per source
python main.py --sources-only

# Full run — fetch, score, send digest
python main.py
```

## Deployment

### Railway.app (recommended — free tier)

1. Fork this repo on GitHub
2. Create a new project on [Railway.app](https://railway.app) → Deploy from GitHub repo
3. Set environment variables in Railway (see below)
4. The `railway.toml` configures a daily cron run automatically

### Google Cloud Run

```bash
gcloud run jobs create job-digest \
  --image gcr.io/your-project/job-digest \
  --schedule "0 7 * * *" \
  --region europe-west1
```

### Docker (local or any host)

```bash
docker build -t job-digest .
docker run --env-file .env job-digest
```

### Windows Task Scheduler (local machine)

Create a task that runs `python main.py` daily at your preferred time.

### Environment variables

All config values can be set as environment variables (useful for deployment without a `config.local.yaml`):

| Variable | Config key |
|----------|-----------|
| `JSEARCH_API_KEY` | `api_keys.jsearch_rapidapi_key` |
| `ADZUNA_APP_ID` | `api_keys.adzuna_app_id` |
| `ADZUNA_APP_KEY` | `api_keys.adzuna_app_key` |
| `TELEGRAM_BOT_TOKEN` | `telegram.bot_token` |
| `TELEGRAM_CHAT_ID` | `telegram.chat_id` |
| `EMAIL_SENDER` | `email.sender_email` |
| `EMAIL_PASSWORD` | `email.sender_password` |
| `EMAIL_RECIPIENT` | `email.recipient_email` |

## Adding a new source

1. Create `sources/your_source.py` with a single public function:
   ```python
   def fetch_jobs(config: dict) -> list[Job]:
       ...
   ```
2. Normalize each result into a `Job` object (see `models.py` for all fields)
3. Register it in `main.py`:
   ```python
   SOURCES = [
       ...
       ("Your Source Name", your_source.fetch_jobs),
   ]
   ```
4. Add tests in `tests/sources/test_your_source.py` — mock all HTTP calls

## Testing

```bash
# Run all tests
python -m pytest tests/ -q

# With verbose output
python -m pytest tests/ -v
```

The test suite (212 tests) runs fully offline — all external APIs and SMTP are mocked. Tests are enforced before every commit via a pre-commit hook.

## Tech stack

- **Python 3.10+** — no heavy frameworks
- `requests` — HTTP calls to job APIs
- `pyyaml` — config loading
- `beautifulsoup4` — HTML scraping (StartupJobs)
- `pytest` + `pytest-mock` — testing
- **Telegram Bot API** — digest delivery
- **Docker** — containerised deployment

## Roadmap

See the [issue tracker](https://github.com/ziv-cohen/job-digest/issues) for planned improvements, including:

- Profile match scoring via LLM (cross-reference job requirements with your CV)
- Hybrid job detection
- Email delivery alongside Telegram
- Additional sources (LinkedIn, Greenhouse, Lever)

## License

MIT
