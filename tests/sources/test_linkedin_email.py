"""Unit tests for sources/linkedin_email.py"""

import email as email_lib
import imaplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import patch

import pytest

from pipeline.health_check import SourceNotConfiguredError
from sources.linkedin_email import (
    fetch_jobs,
    _get_html_body,
    _parse_email_date,
    _parse_linkedin_alert,
)


# ── _parse_email_date ────────────────────────────────────────────

def test_parse_email_date_valid():
    dt = _parse_email_date("Mon, 01 Jun 2025 12:00:00 +0000")
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 6

def test_parse_email_date_invalid_returns_none():
    assert _parse_email_date("not a date") is None

def test_parse_email_date_empty_returns_none():
    assert _parse_email_date("") is None


# ── _get_html_body ───────────────────────────────────────────────

def test_get_html_body_multipart():
    msg = MIMEMultipart("alternative")
    msg.attach(MIMEText("plain text", "plain"))
    msg.attach(MIMEText("<p>html content</p>", "html"))
    # Parse it through the email module as fetch_jobs would receive it
    raw = msg.as_bytes()
    parsed = email_lib.message_from_bytes(raw)
    result = _get_html_body(parsed)
    assert result is not None
    assert "html content" in result

def test_get_html_body_plain_only_returns_none():
    msg = MIMEText("just plain text", "plain")
    raw = msg.as_bytes()
    parsed = email_lib.message_from_bytes(raw)
    assert _get_html_body(parsed) is None

def test_get_html_body_single_html_part():
    msg = MIMEText("<p>only html</p>", "html")
    raw = msg.as_bytes()
    parsed = email_lib.message_from_bytes(raw)
    result = _get_html_body(parsed)
    assert result is not None
    assert "only html" in result


# ── _parse_linkedin_alert ────────────────────────────────────────

def _alert_html(jobs: list[dict]) -> str:
    """Build a minimal LinkedIn-style alert email HTML."""
    cards = ""
    for j in jobs:
        cards += f"""
        <tr>
          <td>
            <a href="{j['url']}">{j['title']}</a>
            <span>{j.get('company', 'Acme')}</span>
            <span>{j.get('location', 'Prague')}</span>
          </td>
        </tr>
        """
    return f"<html><body><table>{cards}</table></body></html>"


def test_parse_linkedin_alert_extracts_jobs():
    html = _alert_html([
        {"title": "Engineering Director", "url": "https://linkedin.com/jobs/view/123", "company": "Stripe"},
        {"title": "Engineering Manager", "url": "https://linkedin.com/jobs/view/456", "company": "Acme"},
    ])
    jobs = _parse_linkedin_alert(html, None)
    assert len(jobs) == 2
    assert jobs[0].source == "linkedin"

def test_parse_linkedin_alert_deduplicates_by_url():
    html = _alert_html([
        {"title": "Engineering Director", "url": "https://linkedin.com/jobs/view/123"},
        {"title": "Engineering Director", "url": "https://linkedin.com/jobs/view/123"},
    ])
    jobs = _parse_linkedin_alert(html, None)
    assert len(jobs) == 1

def test_parse_linkedin_alert_strips_query_params():
    html = _alert_html([
        {"title": "Engineering Director",
         "url": "https://linkedin.com/jobs/view/123?trackingId=abc&refId=xyz"},
    ])
    jobs = _parse_linkedin_alert(html, None)
    assert "?" not in jobs[0].url

def test_parse_linkedin_alert_uses_email_date():
    email_date = datetime(2025, 6, 1, tzinfo=timezone.utc)
    html = _alert_html([
        {"title": "Engineering Director", "url": "https://linkedin.com/jobs/view/123"},
    ])
    jobs = _parse_linkedin_alert(html, email_date)
    assert jobs[0].date_posted == email_date

def test_parse_linkedin_alert_remote_detection():
    html = _alert_html([
        {"title": "Engineering Director", "url": "https://linkedin.com/jobs/view/123",
         "location": "Prague (Remote)"},
    ])
    jobs = _parse_linkedin_alert(html, None)
    assert jobs[0].is_remote is True

def test_parse_linkedin_alert_empty_html():
    jobs = _parse_linkedin_alert("<html><body></body></html>", None)
    assert jobs == []

def test_parse_linkedin_alert_skips_short_titles():
    html = _alert_html([
        {"title": "EM", "url": "https://linkedin.com/jobs/view/999"},  # too short
        {"title": "Engineering Director", "url": "https://linkedin.com/jobs/view/123"},
    ])
    jobs = _parse_linkedin_alert(html, None)
    titles = [j.title for j in jobs]
    assert "Engineering Director" in titles
    assert "EM" not in titles


# ── fetch_jobs ───────────────────────────────────────────────────

def test_fetch_jobs_raises_when_unconfigured_credentials():
    config = {
        "email": {
            "sender_email": "test@gmail.com",
            "sender_password": "YOUR_PASSWORD",
        },
        "search": {"max_age_days": 7},
    }
    with pytest.raises(SourceNotConfiguredError):
        fetch_jobs(config)

def test_fetch_jobs_raises_when_empty_credentials():
    config = {
        "email": {
            "sender_email": "",
            "sender_password": "",
        },
        "search": {"max_age_days": 7},
    }
    with pytest.raises(SourceNotConfiguredError):
        fetch_jobs(config)

def test_fetch_jobs_raises_on_imap_auth_failure():
    config = {
        "email": {"sender_email": "test@gmail.com", "sender_password": "app-password"},
        "search": {"max_age_days": 7},
    }
    with patch("imaplib.IMAP4_SSL") as mock_imap:
        mock_imap.return_value.login.side_effect = imaplib.IMAP4.error("AUTHENTICATIONFAILED")
        with pytest.raises(RuntimeError, match="Gmail IMAP auth failed"):
            fetch_jobs(config)
