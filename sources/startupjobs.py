"""StartupJobs.cz source — JSON API (Czech startup job board)."""

from __future__ import annotations

import logging
import re
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

# Safety cap — the API has ~25 pages of listings (20 results/page = ~490 total)
_MAX_PAGES = 30

# Title must contain at least one of these to be considered relevant.
# The API ignores keyword search (q= is silently ignored), so we filter locally.
_TITLE_KEYWORDS = [
    "engineering", "cto", "chief technology", "vp eng", "vice president eng",
]

# Pre-compiled pattern for stripping HTML tags in description text
_RE_HTML_TAG = re.compile(r"<[^>]+>")


def fetch_jobs(config: dict[str, Any]) -> list[Job]:
    max_age = config["search"]["max_age_days"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age)

    all_jobs: list[Job] = []
    seen_ids: set[int] = set()

    for page in range(1, _MAX_PAGES + 1):
        try:
            resp = requests.get(
                API_URL,
                params={"page": page, "limit": 20},
                headers={"Accept": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.error("StartupJobs.cz request failed for page=%d: %s", page, exc)
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

    logger.info("StartupJobs.cz: %d relevant jobs from %d pages", len(all_jobs), page)
    return all_jobs


def _parse_item(item: dict, cutoff: datetime) -> Job | None:
    title = item.get("name", "").strip()
    url_path = item.get("url", "")
    if not title or not url_path:
        return None

    title_lower = title.lower()
    if not any(kw in title_lower for kw in _TITLE_KEYWORDS):
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
    return _RE_HTML_TAG.sub(" ", html).strip()
