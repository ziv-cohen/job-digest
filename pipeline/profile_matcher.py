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

    api_available = bool(api_key and not api_key.startswith("YOUR_"))
    profile_available = bool(profile_summary and not profile_summary.startswith("YOUR_"))
    can_call_api = api_available and profile_available

    # Load cache — used even when API is not configured
    cache = _load_cache(cache_path)
    client = _make_client(api_key) if can_call_api else None

    if not can_call_api:
        reason = "API key not configured" if not api_available else "profile summary not configured"
        logger.warning("Profile matcher disabled (%s) — cached scores used where available, others default to %.0f",
                       reason, fallback_score)

    cache_hits = sum(1 for job in jobs if job.url in cache)
    api_total = len(jobs) - cache_hits if can_call_api else 0
    if can_call_api and api_total:
        logger.info("Profile matcher: %d from cache, %d to score via API", cache_hits, api_total)
    elif cache_hits:
        logger.info("Profile matcher: %d from cache, %d defaulting to %.0f (API unavailable)",
                    cache_hits, len(jobs) - cache_hits, fallback_score)

    new_entries = 0
    api_done = 0
    for job in jobs:
        if job.url in cache:
            entry = cache[job.url]
            job.score_breakdown["profile_match"] = float(entry["score"])
            job.profile_match_rationale = entry.get("rationale", "")
        elif can_call_api:
            api_done += 1
            logger.info("Scoring [%d/%d]: %s @ %s", api_done, api_total, job.title, job.company)
            score, rationale, success = _call_api(client, model, profile_summary, job, fallback_score)
            job.score_breakdown["profile_match"] = float(score)
            job.profile_match_rationale = rationale
            if success:
                cache[job.url] = {
                    "score": score,
                    "rationale": rationale,
                    "model": model,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                }
                new_entries += 1
        else:
            job.score_breakdown["profile_match"] = fallback_score

    if new_entries:
        _save_cache(cache_path, cache)
        logger.info("Profile matcher: done — %d newly scored, %d from cache", new_entries, cache_hits)
    else:
        logger.info("Profile matcher: all %d jobs served from cache", len(jobs))

    return jobs


def _call_api(client: Any, model: str, profile_summary: str, job: Job,
              fallback_score: float = 50.0) -> tuple[int, str, bool]:
    """Call Claude API for a single job. Returns (score, rationale, success).

    On API or parse error, success=False and score=fallback_score. Callers
    should not cache failed responses so a retry on the next run is possible.
    """
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
            timeout=30,
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Profile match bad JSON for '%s @ %s': %s — raw: %r",
                           job.title, job.company, exc, raw[:200])
            return int(fallback_score), "", False
        score = max(0, min(100, int(data["score"])))
        rationale = str(data.get("rationale", ""))[:80]
        logger.debug("Profile match for '%s @ %s': %d — %s", job.title, job.company, score, rationale)
        return score, rationale, True
    except Exception as exc:
        logger.warning("Profile match API error for '%s @ %s': %s — defaulting to %.0f (fallback)",
                       job.title, job.company, exc, fallback_score)
        return int(fallback_score), "", False


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
