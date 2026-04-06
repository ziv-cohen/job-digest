"""Remotive API source — free, no API key required."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from models import Job

logger = logging.getLogger(__name__)

API_URL = "https://remotive.com/api/remote-jobs"

# Remotive categories that match engineering leadership roles
CATEGORIES = ["software-dev", "all-others"]


def fetch_jobs(config: dict[str, Any]) -> list[Job]:
    """Fetch remote jobs from Remotive and filter for relevant titles."""
    search = config["search"]
    max_age = search["max_age_days"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age)

    # Title keywords to match (case-insensitive)
    title_keywords = [t.lower() for t in search["role_titles"]]

    all_jobs: list[Job] = []

    for category in CATEGORIES:
        try:
            params = {"category": category, "limit": 100}
            resp = requests.get(API_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("jobs", []):
                job = _parse_job(item)
                if job is None:
                    continue
                # Check title relevance
                title_lower = job.title.lower()
                if not any(kw in title_lower for kw in title_keywords):
                    # Also check for common abbreviations
                    if not any(kw in title_lower for kw in [
                        "engineering director", "engineering manager",
                        "director of engineering", "head of engineering",
                        "vp of engineering", "vp engineering",
                        "cto", "chief technology",
                    ]):
                        continue
                # Check age
                if job.date_posted and job.date_posted >= cutoff:
                    all_jobs.append(job)

            logger.info("Remotive: category=%s returned %d total, %d matched", category, len(data.get("jobs", [])), len(all_jobs))

        except requests.RequestException as exc:
            logger.error("Remotive request failed: %s", exc)

    return all_jobs


def _parse_job(item: dict) -> Job | None:
    try:
        title = (item.get("title") or "").strip()
        company = (item.get("company_name") or "").strip()
        url = item.get("url", "")
        if not title or not company:
            return None

        # Location / region
        candidate_location = item.get("candidate_required_location", "")
        is_remote = True  # Remotive is all remote

        # Date
        pub_date = item.get("publication_date", "")
        date_posted = None
        if pub_date:
            try:
                date_posted = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                if date_posted.tzinfo is None:
                    date_posted = date_posted.replace(tzinfo=timezone.utc)
            except ValueError:
                try:
                    date_posted = datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%S")
                    date_posted = date_posted.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

        # Salary
        salary_text = (item.get("salary") or "").strip()

        # Employment type
        job_type = (item.get("job_type") or "").lower()

        # Description
        description = (item.get("description") or "")[:2000]

        return Job(
            title=title,
            company=company,
            url=url,
            source="remotive",
            location=candidate_location or "Remote",
            is_remote=is_remote,
            remote_region=_infer_region(candidate_location),
            date_posted=date_posted,
            salary_text=salary_text,
            description=description,
            employment_type=job_type,
        )
    except Exception as exc:
        logger.debug("Failed to parse Remotive item: %s", exc)
        return None


def _infer_region(location: str) -> str:
    loc = location.lower()
    emea_kw = [
        "europe", "emea", "uk", "united kingdom", "germany", "france",
        "czech", "austria", "switzerland", "ireland", "netherlands",
        "spain", "portugal", "italy", "sweden", "denmark", "norway",
        "finland", "poland", "belgium", "israel", "africa", "middle east",
    ]
    if any(kw in loc for kw in emea_kw):
        return "EMEA"
    if "worldwide" in loc or "anywhere" in loc or "global" in loc or not loc:
        return "Worldwide"
    return ""
