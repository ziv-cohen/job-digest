"""StartupJobs.cz source — JSON API (Czech startup job board)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from models import Job

logger = logging.getLogger(__name__)

BASE_URL = "https://www.startupjobs.cz"
API_URL = f"{BASE_URL}/api/offers"

# All company types on StartupJobs are product/startup companies by definition
_COMPANY_TYPE = "product"

# Map companyType → is_startup flag for growth signal hints
_STARTUP_TYPES = {"start", "growth"}

# Pages to fetch per query (20 results/page)
_MAX_PAGES = 2

_SEARCH_QUERIES = [
    "engineering manager",
    "CTO",
    "director of engineering",
    "head of engineering",
    "VP engineering",
]


def fetch_jobs(config: dict[str, Any]) -> list[Job]:
    max_age = config["search"]["max_age_days"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age)

    all_jobs: list[Job] = []
    seen_ids: set[int] = set()

    for query in _SEARCH_QUERIES:
        for page in range(1, _MAX_PAGES + 1):
            try:
                resp = requests.get(
                    API_URL,
                    params={"q": query, "page": page, "limit": 20},
                    headers={"Accept": "application/json"},
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as exc:
                logger.error("StartupJobs.cz request failed for query=%r page=%d: %s", query, page, exc)
                break

            items = data.get("resultSet", [])
            if not items:
                break

            for item in items:
                job_id = item.get("id")
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                job = _parse_item(item, cutoff)
                if job:
                    all_jobs.append(job)

            paginator = data.get("paginator", {})
            if page >= paginator.get("max", 1):
                break

        logger.info("StartupJobs.cz: query=%r → %d jobs so far", query, len(all_jobs))

    return all_jobs


def _parse_item(item: dict, cutoff: datetime) -> Job | None:
    title = item.get("name", "").strip()
    url_path = item.get("url", "")
    if not title or not url_path:
        return None

    url = url_path if url_path.startswith("http") else BASE_URL + url_path
    company = item.get("company", "").strip()
    location = _parse_location(item)
    is_remote = bool(item.get("isRemote"))
    salary_min, salary_max, currency = _parse_salary(item.get("salary"))

    # Descriptions on StartupJobs are HTML; strip tags for growth signal detection
    desc_html = item.get("description", "")
    desc_text = _strip_html(desc_html)

    return Job(
        title=title,
        company=company,
        url=url,
        source="startupjobs",
        location=location,
        is_remote=is_remote,
        remote_region="EMEA" if is_remote else "",
        date_posted=datetime.now(timezone.utc),  # API doesn't expose date
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=currency,
        description=desc_text[:1000],
        company_type=_COMPANY_TYPE,
    )


def _parse_location(item: dict) -> str:
    raw = item.get("locations", "").strip()
    if not raw or item.get("isRemote"):
        return ""
    # Normalise "Praha" → "Prague, CZ"; keep other Czech cities as-is
    if raw.lower() in ("praha", "prague"):
        return "Prague, CZ"
    return f"{raw}, CZ"


def _parse_salary(salary: dict | None) -> tuple[float | None, float | None, str]:
    """Return (min, max, currency). Converts monthly → annual."""
    if not salary:
        return None, None, ""
    try:
        sal_min = float(salary["min"]) if salary.get("min") else None
        sal_max = float(salary["max"]) if salary.get("max") else None
        currency = salary.get("currency", "").upper()
        if salary.get("measure") == "monthly":
            if sal_min:
                sal_min *= 12
            if sal_max:
                sal_max *= 12
        return sal_min, sal_max, currency
    except (KeyError, TypeError, ValueError):
        return None, None, ""


def _strip_html(html: str) -> str:
    """Remove HTML tags for plain-text description."""
    import re
    return re.sub(r"<[^>]+>", " ", html).strip()
