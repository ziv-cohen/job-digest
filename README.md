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
3. **Scores** each job 0-100 using configurable weighted categories (role, location, company type, seniority, freshness, conditions) — plus an optional LLM-based profile match score
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
│   └── linkedin_email.py    # LinkedIn alerts via Gmail API (gmail.readonly OAuth2)
│
├── pipeline/
│   ├── deduplicator.py      # Fuzzy deduplication (82% similarity threshold)
│   ├── scorer.py            # Weighted scoring engine (0-100 per category)
│   └── profile_matcher.py   # LLM-based profile match scoring (Claude Haiku)
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

Each job is scored 0-100 using a weighted sum of categories. All weights and per-category values are configurable in `config.yaml`.

| Category | Default weight | Key signals |
|----------|---------------|-------------|
| **Profile match** | 45% | LLM-based fit against your `profile.md` (Claude Haiku) |
| **Title match** | 15% | "Engineering Director", "Sr. EM", "EM", "Founding CTO" |
| **Location fit** | 15% | Prague / EMEA remote (100), Czech remote (80), commute tiers |
| **Company type** | 10% | Product company (100), outsourcing (75), consulting (40) |
| **Seniority** | 5% | Director/CTO/VP (100), Senior Manager (80), Manager (55) |
| **Freshness** | 5% | Today (100), yesterday (70), 2-3 days (40), 4-7 days (20) |
| **Conditions** | 5% | Growth signals, salary disclosed, freelancer-friendly |

Weights must sum to 100 (validated at startup). Jobs older than `max_age_days` (default: 7) are hard-filtered before scoring. Jobs where `profile_match = 0` are hard-filtered regardless of total score.

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
| **LinkedIn Email Alerts** | Gmail API credentials | Free — see setup below |

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

### 4. Set up LinkedIn Email Alerts (optional)

This source reads LinkedIn job alert emails from your Gmail inbox using the Gmail API with `gmail.readonly` scope — read-only access only, no write/delete permissions possible.

**Setup:**

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create or select a project
2. Enable the **Gmail API** (APIs & Services → Library → search "Gmail API")
3. Create OAuth2 credentials (APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app)
4. Download the JSON file and save it as `gmail_credentials.json` in the project root
5. **Publish the OAuth app** (APIs & Services → OAuth consent screen → **Publish App**). This is required — apps left in "Testing" status have refresh tokens that expire after 7 days, breaking the pipeline silently. Publishing doesn't make your app publicly listed; it just removes the sandbox restriction. You'll see a "not verified" warning on the consent screen, which is fine for personal use.
6. Add to `config.local.yaml`:
   ```yaml
   linkedin_email:
     credentials_path: "gmail_credentials.json"
     token_path: "gmail_token.json"
   ```
7. In LinkedIn, set your job alert frequency to **Daily** — the pipeline runs once a day and only looks back `max_age_days` (default: 7), so weekly alerts may arrive after jobs have already expired
8. On the first `python main.py --dry-run`, a browser window opens for OAuth2 consent — grant `gmail.readonly` access
9. The token is saved to `gmail_token.json` and auto-refreshed on subsequent pipeline runs

**For deployment on Railway:**

Railway has no browser, so the interactive OAuth consent flow must be completed locally first (steps 1–7 above). The resulting files are then passed to Railway as environment variables — the pipeline writes them to the persistent volume on the first run.

Prerequisites: you have both `gmail_credentials.json` and `gmail_token.json` on your machine.

1. **Attach a persistent volume** to your Railway service (the same one used for `profile_match_cache.json`). Mount it at `/data`.

2. **Set these environment variables** in the Railway dashboard:

   | Variable | Value |
   |----------|-------|
   | `GMAIL_CREDENTIALS_PATH` | `/data/gmail_credentials.json` |
   | `GMAIL_TOKEN_PATH` | `/data/gmail_token.json` |
   | `GMAIL_CREDENTIALS_JSON` | Full contents of your local `gmail_credentials.json` |
   | `GMAIL_TOKEN_JSON` | Full contents of your local `gmail_token.json` |

   On the first run, the pipeline writes the JSON env vars to the configured paths on the volume. On subsequent runs the files already exist and are used directly. The token auto-refreshes and is written back to `/data/gmail_token.json`, so it stays valid indefinitely.

Both credential files are gitignored — never committed.

### 5. Set up your candidate profile (optional but recommended)

The profile matcher uses Claude to score each job against your background. Without it, all jobs get a neutral profile score (50) and the pipeline still works.

**Local setup:**

```bash
cp profile.example.md profile.md   # profile.md is gitignored
# Edit profile.md — fill in your Summary and Full Background sections
```

**Get an Anthropic API key:**
1. Sign up at [platform.claude.com](https://platform.claude.com/)
2. In the left sidebar, click **Manage** → **API Keys** → **Create Key**
3. Add credits: **Settings → Billing** — the API requires a paid balance even for Haiku (a $5 top-up lasts a long time)
4. The profile matcher uses Claude Haiku — very cheap (roughly $0.001 per job scored)

Then add to `config.local.yaml`:

```yaml
anthropic:
  api_key: "your-anthropic-key"

profile_matcher:
  profile_summary: |
    Senior engineering leader with 20 years experience...
    Target roles: Engineering Director, VP Engineering...
    Location: Prague or EMEA remote...
```

**For deployment (Railway, Cloud Run, etc.):**

Set these environment variables instead of using `config.local.yaml`:

| Variable | Value |
|----------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `PROFILE_SUMMARY` | Contents of the `## Summary` section from your `profile.md` |
| `PROFILE_MATCH_CACHE_PATH` | `/data/profile_match_cache.json` (persistent volume path) |

The `profile.md` file itself stays local — never committed, never deployed.

### 6. Customize for yourself

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

### 7. Run it

```bash
# Fetch, score, print results — no message sent (recommended for first run)
python main.py --dry-run

# Just fetch — print raw counts per source
python main.py --sources-only

# Full run — fetch, score, send digest
python main.py

# Ignore a job — it will be excluded from all future runs
python main.py --ignore "https://example.com/job/123"
```

Ignored job URLs are stored in `ignored_jobs.json` locally (gitignored). Each job printed by `--dry-run` includes a ready-to-run ignore command.

**On Railway:** manage the ignore list via the `IGNORED_URLS` environment variable in the Railway dashboard. Set it to a JSON array of URLs:
```json
["https://example.com/job/123", "https://example.com/job/456"]
```
The pipeline merges `IGNORED_URLS` with the local file on every run.

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
| `ANTHROPIC_API_KEY` | `anthropic.api_key` |
| `PROFILE_SUMMARY` | `profile_matcher.profile_summary` |
| `PROFILE_MATCH_CACHE_PATH` | `profile_matcher.cache_path` |
| `GMAIL_CREDENTIALS_PATH` | `linkedin_email.credentials_path` |
| `GMAIL_TOKEN_PATH` | `linkedin_email.token_path` |
| `GMAIL_CREDENTIALS_JSON` | Write credentials JSON to the credentials path on first run |
| `GMAIL_TOKEN_JSON` | Write token JSON to the token path on first run |

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

The test suite runs fully offline — all external APIs and SMTP are mocked. Tests are enforced before every commit via a pre-commit hook.

## Tech stack

- **Python 3.10+** — no heavy frameworks
- `requests` — HTTP calls to job APIs
- `pyyaml` — config loading
- `beautifulsoup4` — HTML scraping (StartupJobs)
- `pytest` + `pytest-mock` — testing
- `anthropic` — Claude Haiku API for profile match scoring
- `google-api-python-client` + `google-auth-oauthlib` — Gmail API (LinkedIn email alerts)
- **Telegram Bot API** — digest delivery
- **Docker** — containerised deployment

## Roadmap

See the [issue tracker](https://github.com/ziv-cohen/job-digest/issues) for planned improvements, including:

- ~~Profile match scoring via LLM~~ — shipped ✓
- Hybrid job detection
- Email delivery alongside Telegram
- Additional sources (LinkedIn, Greenhouse, Lever)

## License

MIT
