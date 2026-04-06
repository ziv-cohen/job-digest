"""Adzuna API source — searches across supported European countries."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from models import Job

logger = logging.getLogger(__name__)

BASE_URL = "https://api.adzuna.com/v1/api/jobs"

# Adzuna country codes relevant for EMEA searches.
# Czech Republic is not officially supported, so we query nearby countries
# that commonly list Prague-compatible remote roles.
COUNTRY_CODES = ["gb", "de", "fr", "nl", "at", "pl"]


def fetch_jobs(config: dict[str, Any]) -> list[Job]:
    """Query Adzuna for each country × role title."""
    app_id = config["api_keys"]["adzuna_app_id"]
    app_key = config["api_keys"]["adzuna_app_key"]
    if not app_id or app_id.startswith("YOUR_"):
        logger.warning("Adzuna API key not configured — skipping source.")
        return []

    search = config["search"]
    role_titles = search["role_titles"]
    max_age = search["max_age_days"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age)

    all_jobs: list[Job] = []

    for country in COUNTRY_CODES:
        for title in role_titles:
            try:
                params = {
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": 20,
                    "what": title,
                    "max_days_old": max_age,
                    "content-type": "application/json",
                    "sort_by": "date",
                }
                url = f"{BASE_URL}/{country}/search/1"
                resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("results", []):
                    job = _parse_job(item, country)
                    if job and job.date_posted and job.date_posted >= cutoff:
                        all_jobs.append(job)

                count = len(data.get("results", []))
                logger.info("Adzuna: country=%s title=%r returned %d results", country, title, count)

            except requests.RequestException as exc:
                logger.error("Adzuna request failed: country=%s title=%r: %s", country, title, exc)

    return all_jobs


def _parse_job(item: dict, country_code: str) -> Job | None:
    try:
        title = item.get("title", "").strip()
        company_info = item.get("company", {})
        company = company_info.get("display_name", "").strip() if isinstance(company_info, dict) else ""
        url = item.get("redirect_url", "")
        if not title or not url:
            return None

        # Location
        location_info = item.get("location", {})
        location = ""
        if isinstance(location_info, dict):
            location = location_info.get("display_name", "")

        # Date
        created = item.get("created", "")
        date_posted = None
        if created:
            try:
                date_posted = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Salary
        salary_min = item.get("salary_min")
        salary_max = item.get("salary_max")
        salary_predicted = item.get("salary_is_predicted", 0)

        # Employment type
        contract_type = (item.get("contract_type") or "").lower()
        contract_time = (item.get("contract_time") or "").lower()

        # Description
        description = (item.get("description") or "")[:2000]

        # Determine if remote from title/description
        text_combined = f"{title} {description}".lower()
        is_remote = any(kw in text_combined for kw in ["remote", "work from home", "distributed", "anywhere"])

        return Job(
            title=title,
            company=company,
            url=url,
            source="adzuna",
            location=location,
            is_remote=is_remote,
            remote_region=_country_to_region(country_code),
            date_posted=date_posted,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=_country_to_currency(country_code),
            salary_is_estimated=bool(salary_predicted),
            description=description,
            employment_type=contract_time or contract_type,
        )
    except Exception as exc:
        logger.debug("Failed to parse Adzuna item: %s", exc)
        return None


def _country_to_region(code: str) -> str:
    return "EMEA"


def _country_to_currency(code: str) -> str:
    return {"gb": "GBP", "de": "EUR", "fr": "EUR", "nl": "EUR", "at": "EUR", "pl": "PLN"}.get(code, "EUR")
