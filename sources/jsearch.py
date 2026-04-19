"""JSearch API source — queries Google for Jobs via RapidAPI."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from models import Job

logger = logging.getLogger(__name__)

RAPIDAPI_HOST = "jsearch.p.rapidapi.com"
SEARCH_URL = f"https://{RAPIDAPI_HOST}/search"


def fetch_jobs(config: dict[str, Any]) -> list[Job]:
    """Query JSearch for each role_title × location combination."""
    api_key = config["api_keys"]["jsearch_rapidapi_key"]
    if not api_key or api_key.startswith("YOUR_"):
        from pipeline.health_check import SourceNotConfiguredError
        raise SourceNotConfiguredError("JSearch API key not configured")

    search = config["search"]
    role_titles = search["role_titles"]
    max_age = search["max_age_days"]
    city = search["locations"]["primary_city"]
    country = search["locations"]["country"]
    region = search["locations"]["region"]

    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": RAPIDAPI_HOST,
    }

    # Build query combinations:
    # 1. Each title + Prague / Czech Republic
    # 2. Each title + "remote" + EMEA
    queries = []
    for title in role_titles:
        queries.append(f"{title} in {city}, {country}")
        queries.append(f"{title} remote {region}")

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age)
    all_jobs: list[Job] = []

    for query in queries:
        try:
            params = {
                "query": query,
                "page": "1",
                "num_pages": "1",
                "results_per_page": "20",
                "date_posted": "week",          # only last 7 days
            }
            resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("data", []):
                job = _parse_job(item)
                if job and job.date_posted and job.date_posted >= cutoff:
                    all_jobs.append(job)

            logger.info("JSearch: query=%r returned %d results", query, len(data.get("data", [])))

        except requests.RequestException as exc:
            logger.error("JSearch request failed for query=%r: %s", query, exc)

    return all_jobs


def _parse_job(item: dict) -> Job | None:
    """Convert a JSearch result item to our Job model."""
    try:
        title = item.get("job_title", "").strip()
        company = item.get("employer_name", "").strip()
        url = item.get("job_apply_link") or item.get("job_google_link", "")
        if not title or not company:
            return None

        # Location
        city = item.get("job_city", "")
        state = item.get("job_state", "")
        country = item.get("job_country", "")
        location_parts = [p for p in [city, state, country] if p]
        location = ", ".join(location_parts)

        is_remote = item.get("job_is_remote", False)

        # Date
        date_str = item.get("job_posted_at_datetime_utc", "")
        date_posted = None
        if date_str:
            try:
                date_posted = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Salary
        salary_min = item.get("job_min_salary")
        salary_max = item.get("job_max_salary")
        salary_currency = item.get("job_salary_currency", "")
        salary_text = item.get("job_salary_period", "")

        # Employment type
        emp_type = (item.get("job_employment_type") or "").lower()

        # Description (truncated for memory)
        description = (item.get("job_description") or "")[:2000]

        return Job(
            title=title,
            company=company,
            url=url,
            source="jsearch",
            location=location,
            is_remote=is_remote,
            remote_region=_infer_remote_region(location, is_remote),
            date_posted=date_posted,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            salary_text=salary_text,
            description=description,
            employment_type=emp_type,
        )
    except Exception as exc:
        logger.debug("Failed to parse JSearch item: %s", exc)
        return None


def _infer_remote_region(location: str, is_remote: bool) -> str:
    """Best-effort inference of remote region from location text."""
    if not is_remote:
        return ""
    loc_lower = location.lower()
    emea_indicators = [
        "europe", "emea", "uk", "united kingdom", "germany", "france",
        "netherlands", "spain", "ireland", "czech", "austria", "switzerland",
        "sweden", "denmark", "norway", "finland", "poland", "portugal",
        "belgium", "italy", "israel", "africa", "middle east",
    ]
    if any(ind in loc_lower for ind in emea_indicators):
        return "EMEA"
    if "worldwide" in loc_lower or "anywhere" in loc_lower or "global" in loc_lower:
        return "Worldwide"
    return ""
