"""LinkedIn email alerts parser — reads Gmail for LinkedIn job alert emails.

Authentication: Gmail API with gmail.readonly OAuth2 scope.
First run: opens a browser for OAuth2 consent. gmail_token.json is saved and
reused on subsequent runs (auto-refreshed — no re-approval needed).
"""

from __future__ import annotations

import base64
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from bs4 import BeautifulSoup

from models import Job

logger = logging.getLogger(__name__)
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_LINKEDIN_SENDERS = ["jobs-noreply@linkedin.com", "jobalerts-noreply@linkedin.com", "jobs-listings@linkedin.com"]
_SEP = "\u00b7"  # middle dot — LinkedIn's company/location separator in alert emails

# Pre-compiled patterns used in HTML parsing — avoids re-compiling on every call
_RE_JOB_URL = re.compile(r"linkedin\.com/(comm/)?jobs/view/\d+")
_RE_QUERY_STRIP = re.compile(r"\?.*$")
_RE_SKIP_LABELS = re.compile(
    r"apply now|see all|similar to|jobs at|jobs in|learn why|unsubscribe|help|message", re.I
)
# Social/status badges LinkedIn appends directly to location text (no separator)
_RE_LOCATION_BADGES = (
    re.compile(r"\d+ connections?", re.I),
    re.compile(r"\d+ school alumni", re.I),
    re.compile(r"Easy Apply", re.I),
    re.compile(r"Actively recruiting", re.I),
    re.compile(r"Fast growing", re.I),
)


def fetch_jobs(config: dict[str, Any]) -> list[Job]:
    """Fetch LinkedIn job alert emails via Gmail API (gmail.readonly scope)."""
    le_cfg = config.get("linkedin_email", {})
    credentials_path = le_cfg.get("credentials_path", "gmail_credentials.json")
    token_path = le_cfg.get("token_path", "gmail_token.json")
    max_age = config["search"]["max_age_days"]

    if not os.path.exists(credentials_path) and not os.path.exists(token_path):
        from pipeline.health_check import SourceNotConfiguredError
        raise SourceNotConfiguredError(
            f"Gmail credentials not found at {credentials_path}"
        )

    try:
        service = _get_gmail_service(credentials_path, token_path)
    except Exception as exc:
        raise RuntimeError(f"Gmail API auth failed: {exc}") from exc

    since_date = (datetime.now() - timedelta(days=max_age)).strftime("%Y/%m/%d")
    sender_query = " OR ".join(f"from:{s}" for s in _LINKEDIN_SENDERS)
    query = f"({sender_query}) after:{since_date}"

    try:
        result = service.users().messages().list(
            userId="me", q=query
        ).execute()
    except Exception as exc:
        raise RuntimeError(f"Gmail API request failed: {exc}") from exc

    messages = result.get("messages", [])
    if not messages:
        logger.info("LinkedIn alerts: no matching emails found.")
        return []

    logger.info("LinkedIn alerts: found %d alert emails", len(messages))
    all_jobs: list[Job] = []

    for msg_ref in messages:
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="full"
            ).execute()
            payload = msg.get("payload", {})
            headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
            email_date = _parse_email_date(headers.get("Date", ""))
            html_body = _extract_html_body(payload)
            if html_body:
                all_jobs.extend(_parse_linkedin_alert(html_body, email_date))
        except Exception as exc:
            logger.debug("Failed to process email %s: %s", msg_ref["id"], exc)

    return all_jobs


def _get_gmail_service(credentials_path: str, token_path: str):
    """Return an authenticated Gmail API service (gmail.readonly scope)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _extract_html_body(payload: dict) -> str | None:
    """Recursively extract the HTML body from a Gmail API message payload."""
    if payload.get("mimeType") == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        result = _extract_html_body(part)
        if result:
            return result
    return None


def _parse_email_date(date_str: str) -> datetime | None:
    """Parse the email Date header into a datetime."""
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def _extract_company_location(title: str, links: list) -> tuple[str, str]:
    """Extract company and location from the combined 'TitleCompany · Location' link text."""
    combined = next(
        (l.get_text(strip=True) for l in links
         if l.get_text(strip=True).startswith(title) and _SEP in l.get_text(strip=True)),
        None,
    )
    if not combined:
        return "", ""
    remainder = combined[len(title):]
    if f" {_SEP} " not in remainder:
        return remainder.strip(), ""
    company_raw, location_raw = remainder.split(f" {_SEP} ", 1)
    company = company_raw.strip()
    # Strip social/status badges appended by LinkedIn directly to location (no separator)
    location = location_raw
    for badge in _RE_LOCATION_BADGES:
        location = badge.sub("", location).strip()
    return company, location


def _parse_linkedin_alert(html: str, email_date: datetime | None) -> list[Job]:
    """Parse job listings from a LinkedIn job alert email."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []

    # Require a numeric job ID — excludes /search?, /collections/, "see all" links, etc.
    job_links = soup.find_all("a", href=_RE_JOB_URL)

    # Group all links by clean URL so we can pick the best title per job
    url_links: dict[str, list] = defaultdict(list)
    for link in job_links:
        url = _RE_QUERY_STRIP.sub("", link.get("href", "").rstrip("/"))
        if url:
            url_links[url].append(link)

    for url, links in url_links.items():
        try:
            # Pick shortest clean text — title-only links are always shorter than
            # the combined "TitleCompanyLocation" or "Jobs similar to X at Y" links
            candidates = [l.get_text(strip=True) for l in links]
            title = next(
                (t for t in sorted(candidates, key=len) if len(t) >= 5 and not _RE_SKIP_LABELS.search(t)),
                None,
            )
            if not title:
                continue

            # Extract company and location from the combined "TitleCompany · Location" link
            company, location = _extract_company_location(title, links)
            if not company:
                company = "Unknown (LinkedIn)"

            # Check remote
            combined_text = f"{title} {location}".lower()
            is_remote = any(kw in combined_text for kw in ["remote", "hybrid", "work from home"])

            jobs.append(Job(
                title=title,
                company=company,
                url=url,
                source="linkedin",
                location=location,
                is_remote=is_remote,
                remote_region="",
                date_posted=email_date or datetime.now(timezone.utc),
                description="",
            ))

        except Exception as exc:
            logger.debug("Failed to parse LinkedIn job link: %s", exc)

    return jobs
