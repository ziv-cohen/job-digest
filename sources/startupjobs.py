"""StartupJobs.cz source — lightweight scraping of public job listings."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from models import Job

logger = logging.getLogger(__name__)

BASE_URL = "https://www.startupjobs.cz"
SEARCH_URL = f"{BASE_URL}/nabidky"

# English site variant
EN_BASE_URL = "https://www.startupjobs.cz/en"
EN_SEARCH_URL = f"{EN_BASE_URL}/offers"


def fetch_jobs(config: dict[str, Any]) -> list[Job]:
    """Fetch management/director roles from StartupJobs.cz."""
    search = config["search"]
    max_age = search["max_age_days"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age)

    title_keywords = [t.lower() for t in search["role_titles"]]
    # Additional CZ-market keywords
    title_keywords.extend([
        "engineering director", "engineering manager", "head of engineering",
        "vp engineering", "cto", "chief technology officer",
        "ředitel", "vedoucí",  # Czech equivalents
    ])

    all_jobs: list[Job] = []

    # Try the English search page with management/leadership filters
    search_queries = [
        "engineering director",
        "engineering manager",
        "CTO",
        "head of engineering",
    ]

    for query in search_queries:
        try:
            # StartupJobs.cz uses query params for search
            params = {"q": query}
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; JobDigest/1.0; personal use)",
                "Accept-Language": "en,cs;q=0.9",
            }
            resp = requests.get(EN_SEARCH_URL, params=params, headers=headers, timeout=15)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            job_cards = soup.select("article, .offer, [data-offer], .job-card, .listing")

            for card in job_cards:
                job = _parse_card(card, query)
                if job:
                    all_jobs.append(job)

            logger.info("StartupJobs.cz: query=%r found %d cards", query, len(job_cards))

        except requests.RequestException as exc:
            logger.error("StartupJobs.cz request failed for query=%r: %s", query, exc)

    # Deduplicate within source by URL
    seen_urls: set[str] = set()
    unique_jobs = []
    for job in all_jobs:
        if job.url not in seen_urls:
            seen_urls.add(job.url)
            unique_jobs.append(job)

    return unique_jobs


def _parse_card(card, query: str) -> Job | None:
    """Parse a single job card element from StartupJobs.cz HTML."""
    try:
        # Try to find the title link
        title_el = card.select_one("h2 a, h3 a, .title a, a[href*='/nabidka'], a[href*='/offer']")
        if not title_el:
            title_el = card.select_one("a")
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        if href and not href.startswith("http"):
            href = BASE_URL + href

        # Company
        company_el = card.select_one(".company, .company-name, [class*='company']")
        company = company_el.get_text(strip=True) if company_el else ""

        # Location
        location_el = card.select_one(".location, [class*='location'], [class*='place']")
        location = location_el.get_text(strip=True) if location_el else "Prague, CZ"

        # Check for remote indicators
        card_text = card.get_text().lower()
        is_remote = any(kw in card_text for kw in ["remote", "práce z domova", "home office"])

        if not title or not href:
            return None

        return Job(
            title=title,
            company=company,
            url=href,
            source="startupjobs",
            location=location,
            is_remote=is_remote,
            remote_region="" if not is_remote else "EMEA",
            date_posted=datetime.now(timezone.utc),  # StartupJobs doesn't always show date
            description=card_text[:1000],
            company_type="product",  # StartupJobs focuses on startups = product companies
        )
    except Exception as exc:
        logger.debug("Failed to parse StartupJobs card: %s", exc)
        return None
