"""Deduplicate jobs across sources using fuzzy title + company matching."""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any

from models import Job

logger = logging.getLogger(__name__)

TITLE_SIMILARITY_THRESHOLD = 0.82       # titles this similar → treat as duplicate
COMPANY_SIMILARITY_MIN = 0.75           # company must clear this before title is even checked
COMPANY_SIMILARITY_SUBSTRING = 0.80    # stricter gate for substring-based title matching


def deduplicate(jobs: list[Job], config: dict[str, Any] | None = None) -> list[Job]:
    """Remove duplicate jobs, keeping the one with the highest-quality source.

    Priority: jsearch > adzuna > remotive > linkedin > startupjobs
    (JSearch/Adzuna have richer structured data.)
    """
    source_priority = {
        "jsearch": 5,
        "adzuna": 4,
        "remotive": 3,
        "linkedin": 2,
        "startupjobs": 1,
    }

    # Generate dedup keys
    for job in jobs:
        job.dedup_key = _make_dedup_key(job)

    # Group by dedup key, keep best source
    groups: dict[str, list[Job]] = {}
    for job in jobs:
        key = job.dedup_key
        # Check for fuzzy matches against existing groups
        matched_key = _find_fuzzy_match(key, groups.keys())
        if matched_key:
            groups[matched_key].append(job)
        else:
            groups[key] = [job]

    # Select the best job from each group
    unique_jobs: list[Job] = []
    for key, group in groups.items():
        # Sort by source priority (highest first), then by description length
        group.sort(key=lambda j: (source_priority.get(j.source, 0), len(j.description)), reverse=True)
        best = group[0]
        # Merge in extra info from duplicates if best is missing it
        for other in group[1:]:
            if not best.salary_text and other.salary_text:
                best.salary_text = other.salary_text
            if not best.salary_min and other.salary_min:
                best.salary_min = other.salary_min
                best.salary_max = other.salary_max
                best.salary_currency = other.salary_currency
            if not best.description and other.description:
                best.description = other.description
        unique_jobs.append(best)

    removed = len(jobs) - len(unique_jobs)
    logger.info("Deduplication: %d jobs in → %d unique (%d duplicates removed)", len(jobs), len(unique_jobs), removed)

    return unique_jobs


def _make_dedup_key(job: Job) -> str:
    """Create a normalised key from title + company for comparison."""
    title = _normalise(job.title)
    company = _normalise(job.company)
    return f"{title}||{company}"


def _normalise(text: str) -> str:
    """Lowercase, strip non-alphanumeric, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _find_fuzzy_match(key: str, existing_keys) -> str | None:
    """Check if *key* fuzzy-matches any existing group key."""
    title_a, company_a = key.split("||", 1)

    for existing in existing_keys:
        title_b, company_b = existing.split("||", 1)

        # Company must be reasonably similar
        company_sim = SequenceMatcher(None, company_a, company_b).ratio()
        if company_sim < COMPANY_SIMILARITY_MIN:
            continue

        # Title must be similar
        title_sim = SequenceMatcher(None, title_a, title_b).ratio()
        if title_sim >= TITLE_SIMILARITY_THRESHOLD:
            return existing

        # Also check if one title contains the other (e.g., "Engineering Director"
        # vs "Engineering Director - Data Platform")
        if title_a in title_b or title_b in title_a:
            if company_sim >= COMPANY_SIMILARITY_SUBSTRING:
                return existing

    return None
