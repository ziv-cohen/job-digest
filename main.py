"""Job Digest Pipeline — main orchestrator.

Usage:
    python main.py                  # Run full pipeline
    python main.py --dry-run        # Fetch + score, print results, don't send
    python main.py --sources-only   # Fetch only, print raw counts
    python main.py --resend         # Re-send digest from dry_run_results.json (no API calls)
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows (avoids cp1252 errors with non-ASCII job data)
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_config
from models import Job
from sources import jsearch, adzuna, remotive, startupjobs, linkedin_email
from pipeline.deduplicator import deduplicate
from pipeline.scorer import score_jobs
from output.email_digest import send_digest as send_email_digest
from output.telegram_digest import send_digest as send_telegram_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# ── Source registry ────────────────────────────────────────────

SOURCES = [
    ("JSearch (Google Jobs)", jsearch.fetch_jobs),
    ("Adzuna", adzuna.fetch_jobs),
    ("Remotive", remotive.fetch_jobs),
    ("StartupJobs.cz", startupjobs.fetch_jobs),
    ("LinkedIn Email Alerts", linkedin_email.fetch_jobs),
]


def resend() -> None:
    """Re-send the digest from the last dry_run_results.json without fetching."""
    config = load_config(Path(__file__).resolve().parent)
    cache_path = Path(__file__).resolve().parent / "dry_run_results.json"
    if not cache_path.exists():
        logger.error("No cache found at %s — run with --dry-run first.", cache_path)
        sys.exit(1)
    with open(cache_path) as f:
        jobs = [Job.from_dict(d) for d in json.load(f)]
    logger.info("Loaded %d jobs from cache — sending digest.", len(jobs))
    tg_token = config.get("telegram", {}).get("bot_token", "")
    if tg_token and not tg_token.startswith("YOUR_"):
        sent = send_telegram_digest(jobs, config)
    else:
        sent = send_email_digest(jobs, config)
    if sent:
        logger.info("Digest re-sent with %d jobs.", len(jobs))
    else:
        logger.error("All output channels failed!")
        sys.exit(1)


def run(dry_run: bool = False, sources_only: bool = False) -> None:
    """Execute the full pipeline."""
    config = load_config(Path(__file__).resolve().parent)

    # ── 1. Fetch from all sources ──
    logger.info("=" * 60)
    logger.info("Job Digest Pipeline — %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    logger.info("=" * 60)

    all_jobs: list[Job] = []
    for name, fetcher in SOURCES:
        logger.info("Fetching from %s …", name)
        try:
            jobs = fetcher(config)
            logger.info("  → %d jobs fetched", len(jobs))
            all_jobs.extend(jobs)
        except Exception as exc:
            logger.error("  → FAILED: %s", exc)

    logger.info("Total raw jobs: %d", len(all_jobs))

    if sources_only:
        _print_source_summary(all_jobs)
        return

    if not all_jobs:
        logger.warning("No jobs found from any source. Check your API keys and network.")
        return

    # ── 2. Deduplicate ──
    unique_jobs = deduplicate(all_jobs, config)

    # ── 3. Score ──
    scored_jobs = score_jobs(unique_jobs, config)

    # ── 4. Filter by minimum score and non-zero title score ──
    min_score = config["scoring"]["min_score"]
    filtered = [
        j for j in scored_jobs
        if j.score >= min_score and j.score_breakdown.get("title", 0) > 0
    ]
    logger.info("After filtering (score >= %d, title > 0): %d jobs", min_score, len(filtered))

    # ── 4b. Filter by minimum salary (only when salary is disclosed) ──
    min_salary_cfg = config["scoring"].get("min_salary", {})
    if min_salary_cfg:
        before = len(filtered)
        filtered = [j for j in filtered if _salary_above_minimum(j, min_salary_cfg)]
        logger.info("After salary filter: %d jobs (%d removed)", len(filtered), before - len(filtered))

    # ── 5. Sort by score descending ──
    filtered.sort(key=lambda j: j.score, reverse=True)

    # ── 6. Apply max limit (0 = no limit) ──
    max_jobs = config["output"].get("max_jobs_in_digest", 0)
    if max_jobs > 0:
        filtered = filtered[:max_jobs]

    # ── 7. Output ──
    if dry_run:
        _print_dry_run(filtered)
        # Also save JSON for inspection
        output_path = Path(__file__).resolve().parent / "dry_run_results.json"
        with open(output_path, "w") as f:
            json.dump([j.to_dict() for j in filtered], f, indent=2, default=str)
        logger.info("Dry run results saved to %s", output_path)
    else:
        tg_token = config.get("telegram", {}).get("bot_token", "")
        if tg_token and not tg_token.startswith("YOUR_"):
            sent = send_telegram_digest(filtered, config)
        else:
            sent = send_email_digest(filtered, config)
        if sent:
            logger.info("Pipeline complete — digest sent with %d jobs.", len(filtered))
        else:
            logger.error("Pipeline complete but all output channels failed!")
            sys.exit(1)


def _salary_above_minimum(job: Job, min_salary: dict) -> bool:
    """Return True if the job passes the minimum salary filter.

    Jobs with no disclosed salary are always kept — we can't disqualify what we don't know.
    Only filters when salary_max is present and currency is in our threshold map.
    """
    if not job.salary_max or not job.salary_currency:
        return True
    currency = job.salary_currency.strip().upper()
    threshold = min_salary.get(currency)
    if threshold is None:
        return True  # unknown currency — keep the job
    return job.salary_max >= threshold


def _print_source_summary(jobs: list[Job]) -> None:
    """Print count per source."""
    from collections import Counter
    counts = Counter(j.source for j in jobs)
    print("\n--- Source Summary ---")
    for source, count in counts.most_common():
        print(f"  {source:20s} {count:4d} jobs")
    print(f"  {'TOTAL':20s} {len(jobs):4d} jobs")


def _print_dry_run(jobs: list[Job]) -> None:
    """Pretty-print scored jobs to stdout."""
    print(f"\n{'='*80}")
    print(f"DRY RUN RESULTS — {len(jobs)} jobs passing threshold")
    print(f"{'='*80}\n")

    for i, job in enumerate(jobs, 1):
        remote_tag = " [Remote]" if job.is_remote else ""
        region_tag = f" ({job.remote_region})" if job.remote_region else ""
        salary = job.salary_text or job._salary_range() or "Not disclosed"

        print(f"#{i:2d}  [{job.score:5.1f} pts]  {job.title}")
        print(f"     Company:  {job.company}")
        print(f"     Location: {job.location}{remote_tag}{region_tag}")
        print(f"     Salary:   {salary}")
        growth_tag = "  | Growing company" if job.has_growth_signals else ""
        print(f"     Type:     {job.company_type or 'unknown'}  |  Seniority: {job.seniority or 'unknown'}{growth_tag}")
        print(f"     Posted:   {job.date_posted.strftime('%d %b %Y') if job.date_posted else 'N/A'}  |  Source: {job.source}")
        print(f"     URL:      {job.url}")
        breakdown = " | ".join(f"{k}: {v:.0f}" for k, v in job.score_breakdown.items() if v > 0)
        print(f"     Score:    {breakdown}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Job Digest Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and score but don't send")
    parser.add_argument("--sources-only", action="store_true", help="Fetch only, show counts per source")
    parser.add_argument("--resend", action="store_true", help="Re-send digest from dry_run_results.json (no API calls)")
    args = parser.parse_args()
    if args.resend:
        resend()
    else:
        run(dry_run=args.dry_run, sources_only=args.sources_only)


if __name__ == "__main__":
    main()
