# Job Digest Pipeline

## Project Overview
A daily automated job search pipeline that queries multiple job APIs, deduplicates results, scores them against Ziv's criteria, and sends a ranked email digest every morning.

## Target User
Ziv Cohen — Senior Engineering Leader (20 years experience), recently relocated from Israel to Prague, Czech Republic. Looking for: Engineering Director, Senior EM, EM (at fast-growing companies), or Founding CTO roles. Open to Prague on-site/hybrid, Czech Republic remote, or EMEA remote. EMEA remote is preferred over Czech remote due to higher salaries.

## Architecture
```
Sources → Normalize → Deduplicate → Score → Filter (≥40 pts, ≤7 days) → Sort (desc) → Email
```

### Sources (in `sources/`)
1. **JSearch** (Google Jobs via RapidAPI) — broadest coverage, aggregates LinkedIn/Indeed/Glassdoor
2. **Adzuna** — European job aggregator with proper API (GB, DE, FR, NL, AT, PL)
3. **Remotive** — free API, remote jobs only
4. **StartupJobs.cz** — Czech startup scene, HTML scraping
5. **LinkedIn Email Alerts** — parses Gmail IMAP for LinkedIn alert emails

### Pipeline (in `pipeline/`)
- `deduplicator.py` — fuzzy matching on normalized title+company (82% threshold)
- `scorer.py` — 100-point scoring: title(30) + location(25) + company_type(20) + seniority(15) + freshness(10) + bonus

### Output (in `output/`)
- `email_digest.py` — HTML + plaintext email via SMTP

## Key Scoring Rules
- EMEA remote = Prague on-site/hybrid = 25 points (EMEA remote pays more)
- Czech remote = 20 points
- Jobs older than 7 days are HARD FILTERED (not scored, removed entirely)
- Freshness: today=10, yesterday=7, 2-3 days=4, 4-7 days=2
- EM role gets +5 bonus if company shows growth signals
- Freelancer-friendly, salary disclosed, growth signals each add bonus points

## Configuration
- `config.yaml` — defaults and structure (committed)
- `config.local.yaml` — secrets and overrides (gitignored)
- Environment variables also supported (see config_loader.py)

## Commands
```bash
python main.py --dry-run        # Test: fetch, score, print — no email
python main.py --sources-only   # Test: just fetch, show counts
python main.py                  # Full run: fetch, score, email
```

## Dependencies
- Python 3.10+
- requests, pyyaml, beautifulsoup4
- No heavy frameworks — lightweight and fast

## Deployment
Designed for Railway.app free tier or Google Cloud Run with a daily cron trigger.
Can also run locally via Windows Task Scheduler.

## Development Notes
- When adding a new source: create `sources/new_source.py` with `fetch_jobs(config) -> list[Job]`, then register in `main.py` SOURCES list
- All jobs normalize to the `Job` dataclass in `models.py`
- Scoring weights are fully configurable in `config.yaml`
- The pipeline is idempotent — safe to run multiple times per day

## Testing
- Every module with logic must have a corresponding `tests/test_<module>.py`
- External dependencies (HTTP APIs, IMAP, SMTP) must be mocked — tests must run offline
- Use `pytest-mock` (`mocker` fixture) for mocking; `unittest.mock.patch` is also fine
- Run `python -m pytest tests/ -q` before committing — pre-commit hook enforces this
- Test file map:
  - `pipeline/deduplicator.py` → `tests/test_deduplicator.py` ✓
  - `pipeline/scorer.py` → `tests/test_scorer.py`
  - `sources/jsearch.py` → `tests/sources/test_jsearch.py`
  - `sources/adzuna.py` → `tests/sources/test_adzuna.py`
  - `sources/remotive.py` → `tests/sources/test_remotive.py`
  - `config_loader.py` → `tests/test_config_loader.py`
