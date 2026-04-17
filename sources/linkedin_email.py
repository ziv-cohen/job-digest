"""LinkedIn email alerts parser — reads Gmail for LinkedIn job alert emails."""

from __future__ import annotations

import email
import imaplib
import logging
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from typing import Any

from bs4 import BeautifulSoup

from models import Job

logger = logging.getLogger(__name__)


def fetch_jobs(config: dict[str, Any]) -> list[Job]:
    """Connect to Gmail via IMAP, find LinkedIn alert emails, parse job listings."""
    email_cfg = config["email"]
    sender_email = email_cfg.get("sender_email", "")
    sender_password = email_cfg.get("sender_password", "")
    max_age = config["search"]["max_age_days"]

    if not sender_email or not sender_password or sender_password.startswith("YOUR_"):
        from pipeline.health_check import SourceNotConfiguredError
        raise SourceNotConfiguredError("Email credentials not configured")

    all_jobs: list[Job] = []

    try:
        # Connect to Gmail IMAP
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(sender_email, sender_password)
        mail.select("inbox")

        # Search for LinkedIn job alert emails from the last N days
        since_date = (datetime.now() - timedelta(days=max_age)).strftime("%d-%b-%Y")
        search_query = f'(FROM "jobs-noreply@linkedin.com" SINCE {since_date})'

        status, message_ids = mail.search(None, search_query)
        if status != "OK" or not message_ids[0]:
            logger.info("LinkedIn alerts: no matching emails found.")
            mail.logout()
            return []

        ids = message_ids[0].split()
        logger.info("LinkedIn alerts: found %d alert emails", len(ids))

        # Process last 20 emails max (most recent)
        for msg_id in ids[-20:]:
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Get email date
                email_date = _parse_email_date(msg.get("Date", ""))

                # Extract HTML body
                html_body = _get_html_body(msg)
                if not html_body:
                    continue

                # Parse job listings from HTML
                jobs = _parse_linkedin_alert(html_body, email_date)
                all_jobs.extend(jobs)

            except Exception as exc:
                logger.debug("Failed to process email %s: %s", msg_id, exc)

        mail.logout()

    except imaplib.IMAP4.error as exc:
        logger.error("IMAP connection failed: %s", exc)
    except Exception as exc:
        logger.error("LinkedIn alerts fetch failed: %s", exc)

    return all_jobs


def _get_html_body(msg) -> str | None:
    """Extract HTML body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    else:
        if msg.get_content_type() == "text/html":
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
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

    # LinkedIn alert emails typically contain job cards as table rows or divs
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
