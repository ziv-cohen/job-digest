"""Profile match scoring — scores each job against the candidate profile via Claude API."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import Job

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are evaluating job fit for a senior engineering leader.

CANDIDATE PROFILE:
{profile_summary}

JOB:
Title: {title}
Company: {company}
Location: {location}{remote_tag}
Salary: {salary}
Description:
{description}

Score this job 0-100 for profile fit:
- 0: clearly wrong domain/level (sales, hardware, junior, non-engineering)
- 40: possible but weak (wrong seniority, unclear scope, weak domain match)
- 70: good match (right level, relevant domain)
- 90-100: excellent match (ideal role, strong signals for this candidate)

Respond ONLY with valid JSON: {{"score": <int 0-100>, "rationale": "<one concise line max 80 chars>"}}"""


def match_profile(jobs: list[Job], config: dict[str, Any]) -> list[Job]:
    """Score each job against the candidate profile using Claude API.

    Mutates job.score_breakdown['profile_match'] and job.profile_match_rationale.
    Does NOT recompute job.score — call scorer.recompute_scores() afterwards.
    Cached by URL — jobs already in cache are not re-scored.
    """
    matcher_cfg = config.get("profile_matcher", {})
    anthropic_cfg = config.get("anthropic", {})
    api_key = anthropic_cfg.get("api_key", "")
    model = anthropic_cfg.get("model", "claude-haiku-4-5-20251001")
    profile_summary = matcher_cfg.get("profile_summary", "")
    cache_path = Path(matcher_cfg.get("cache_path", "profile_match_cache.json"))
    fallback_score = float(matcher_cfg.get("fallback_score", 50))

    # Graceful degradation — no API key or placeholder profile
    api_available = bool(api_key and not api_key.startswith("YOUR_"))
    profile_available = bool(profile_summary and not profile_summary.startswith("YOUR_"))

    if not api_available or not profile_available:
        reason = "API key not configured" if not api_available else "profile summary not configured"
        logger.warning("Profile matcher disabled (%s) — setting all profile_match scores to %.0f (fallback)",
                       reason, fallback_score)
        for job in jobs:
            job.score_breakdown["profile_match"] = fallback_score
        return jobs

    # Load cache
    cache = _load_cache(cache_path)
    client = _make_client(api_key)

    new_entries = 0
    for job in jobs:
        if job.url in cache:
            entry = cache[job.url]
            job.score_breakdown["profile_match"] = float(entry["score"])
            job.profile_match_rationale = entry.get("rationale", "")
            logger.debug("Cache hit for %s", job.url)
        else:
            score, rationale = _call_api(client, model, profile_summary, job, fallback_score)
            job.score_breakdown["profile_match"] = float(score)
            job.profile_match_rationale = rationale
            cache[job.url] = {
                "score": score,
                "rationale": rationale,
                "model": model,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            new_entries += 1

    if new_entries:
        _save_cache(cache_path, cache)
        logger.info("Profile matcher: scored %d new jobs, %d from cache",
                    new_entries, len(jobs) - new_entries)
    else:
        logger.info("Profile matcher: all %d jobs served from cache", len(jobs))

    return jobs


def _call_api(client: Any, model: str, profile_summary: str, job: Job,
              fallback_score: float = 50.0) -> tuple[int, str]:
    """Call Claude API for a single job. Returns (score, rationale)."""
    remote_tag = " (Remote)" if job.is_remote else ""
    salary = job.salary_text or "Not disclosed"
    description = (job.description or "")[:3000]

    prompt = _PROMPT_TEMPLATE.format(
        profile_summary=profile_summary,
        title=job.title,
        company=job.company,
        location=job.location or "Not specified",
        remote_tag=remote_tag,
        salary=salary,
        description=description,
    )

    try:
        message = client.messages.create(
            model=model,
            max_tokens=128,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        data = json.loads(raw)
        score = max(0, min(100, int(data["score"])))
        rationale = str(data.get("rationale", ""))[:80]
        logger.debug("Profile match for '%s @ %s': %d — %s", job.title, job.company, score, rationale)
        return score, rationale
    except Exception as exc:
        logger.warning("Profile match API error for '%s @ %s': %s — defaulting to %.0f (fallback)",
                       job.title, job.company, exc, fallback_score)
        return int(fallback_score), ""


def _make_client(api_key: str) -> Any:
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def _load_cache(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Could not load profile match cache: %s", exc)
    return {}


def _save_cache(path: Path, cache: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.warning("Could not save profile match cache: %s", exc)
