# TODO

## Scoring

- [ ] **Profile match scoring (high impact)** — Parse job description requirements and cross-reference against Ziv's profile (20yr engineering leadership, Israeli→Prague relocation, Director/Sr.EM/EM/Founding CTO target roles, product-company preference, EMEA remote). Produce a match score that carries meaningful weight in the total (suggest 20–30 pts, comparable to location today). Likely requires an LLM call per job (e.g. Claude Haiku for cost efficiency) with a structured prompt that returns a score + rationale. Key design decisions: where to call (new `pipeline/profile_matcher.py`), caching to avoid re-scoring known jobs, prompt design to return consistent numeric output, and how to surface the rationale in the digest.
- [ ] Hybrid jobs from JSearch may have `is_remote=False` (API flag doesn't distinguish hybrid from on-site). Fix `_score_location` to also detect "hybrid" keyword in job text, not rely solely on `is_remote`.

## Testing

- [ ] Fix all warnings from the test suite (`python -m pytest tests/ -q` currently shows 128 warnings, all `datetime.utcnow()` deprecations)
- [ ] Once warnings are fixed, add `-W error` flag to pytest runs so future warnings are treated as errors
- [ ] Code review all test files for quality, coverage gaps, and consistency

## Sources

- [ ] StartupJobs.cz (`sources/startupjobs.py`) — broken, site returns 404. URL may have changed or scraping is blocked. Investigate and fix or replace with their API if available.
- [ ] LinkedIn email alerts (`sources/linkedin_email.py`) — parked for now. JSearch and Adzuna aggregate LinkedIn jobs already. Revisit if coverage feels thin. Implementation requires Gmail app password or OAuth2 readonly scope (see earlier discussion).

## Output

- [ ] Send digest to email — current primary output is Telegram. Add email delivery as a parallel channel or fallback. SMTP is already implemented in `output/email_digest.py`; needs sender credentials configured in `config.local.yaml`.

## Infrastructure

- [x] Automated daily run — deployed on Railway.app, cron `0 7 * * *` (8:00 AM Prague time)
- [ ] Integrate TODO list with external board (Linear / GitHub Issues / Jira)
