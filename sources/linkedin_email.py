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
from datetime import datetime, timedelta, timezone
from typing import Any

from bs4 import BeautifulSoup

from models import Job

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_LINKEDIN_SENDER = "jobs-noreply@linkedin.com"


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
    query = f"from:{_LINKEDIN_SENDER} after:{since_date}"

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


def _parse_linkedin_alert(html: str, email_date: datetime | None) -> list[Job]:
    """Parse job listings from a LinkedIn job alert email."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []

    # LinkedIn alert emails contain job cards as table rows or divs
    # with links to linkedin.com/jobs/view/...
    job_links = soup.find_all("a", href=re.compile(r"linkedin\.com/jobs/view|linkedin\.com/comm/jobs"))

    seen_urls: set[str] = set()
    for link in job_links:
        try:
            url = link.get("href", "")
            # Clean tracking params
            url = re.sub(r"\?.*$", "", url)

            if url in seen_urls or not url:
                continue
            seen_urls.add(url)

            # Title is usually the link text
            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Company is typically in a nearby element
            parent = link.find_parent(["tr", "td", "div", "table"])
            company = ""
            location = ""
            if parent:
                text_parts = parent.get_text(separator="|", strip=True).split("|")
                # Heuristic: title is first, company second, location third
                for part in text_parts:
                    part = part.strip()
                    if part == title:
                        continue
                    if not company and len(part) > 2 and not any(c in part for c in ["@", "http"]):
                        company = part
                    elif not location and len(part) > 2:
                        location = part

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
