"""Unit tests for sources/linkedin_email.py"""

import base64
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from pipeline.health_check import SourceNotConfiguredError
from sources.linkedin_email import (
    fetch_jobs,
    _extract_html_body,
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


# ── _extract_html_body ───────────────────────────────────────────

def _b64(html: str) -> str:
    return base64.urlsafe_b64encode(html.encode()).decode()

def test_extract_html_body_simple():
    payload = {"mimeType": "text/html", "body": {"data": _b64("<p>hello</p>")}, "parts": []}
    assert "hello" in _extract_html_body(payload)

def test_extract_html_body_multipart():
    payload = {
        "mimeType": "multipart/alternative",
        "body": {},
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _b64("plain")}, "parts": []},
            {"mimeType": "text/html",  "body": {"data": _b64("<p>html</p>")}, "parts": []},
        ],
    }
    assert "html" in _extract_html_body(payload)

def test_extract_html_body_no_html_returns_none():
    payload = {
        "mimeType": "multipart/alternative",
        "body": {},
        "parts": [{"mimeType": "text/plain", "body": {"data": _b64("plain")}, "parts": []}],
    }
    assert _extract_html_body(payload) is None

def test_extract_html_body_nested():
    inner = {"mimeType": "text/html", "body": {"data": _b64("<p>deep</p>")}, "parts": []}
    outer = {"mimeType": "multipart/mixed", "body": {}, "parts": [
        {"mimeType": "multipart/alternative", "body": {}, "parts": [inner]},
    ]}
    assert "deep" in _extract_html_body(outer)


# ── _parse_linkedin_alert ────────────────────────────────────────

def _alert_html(jobs: list[dict]) -> str:
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
        {"title": "Engineering Manager",  "url": "https://linkedin.com/jobs/view/456", "company": "Acme"},
    ])
    jobs = _parse_linkedin_alert(html, None)
    assert len(jobs) == 2
    assert jobs[0].source == "linkedin"

def test_parse_linkedin_alert_deduplicates_by_url():
    html = _alert_html([
        {"title": "Engineering Director", "url": "https://linkedin.com/jobs/view/123"},
        {"title": "Engineering Director", "url": "https://linkedin.com/jobs/view/123"},
    ])
    assert len(_parse_linkedin_alert(html, None)) == 1

def test_parse_linkedin_alert_strips_query_params():
    html = _alert_html([
        {"title": "Engineering Director",
         "url": "https://linkedin.com/jobs/view/123?trackingId=abc&refId=xyz"},
    ])
    assert "?" not in _parse_linkedin_alert(html, None)[0].url

def test_parse_linkedin_alert_uses_email_date():
    email_date = datetime(2025, 6, 1, tzinfo=timezone.utc)
    html = _alert_html([{"title": "Engineering Director", "url": "https://linkedin.com/jobs/view/123"}])
    assert _parse_linkedin_alert(html, email_date)[0].date_posted == email_date

def test_parse_linkedin_alert_remote_detection():
    html = _alert_html([
        {"title": "Engineering Director", "url": "https://linkedin.com/jobs/view/123",
         "location": "Prague (Remote)"},
    ])
    assert _parse_linkedin_alert(html, None)[0].is_remote is True

def test_parse_linkedin_alert_empty_html():
    assert _parse_linkedin_alert("<html><body></body></html>", None) == []

def test_parse_linkedin_alert_skips_short_titles():
    html = _alert_html([
        {"title": "EM",                   "url": "https://linkedin.com/jobs/view/999"},
        {"title": "Engineering Director", "url": "https://linkedin.com/jobs/view/123"},
    ])
    titles = [j.title for j in _parse_linkedin_alert(html, None)]
    assert "Engineering Director" in titles
    assert "EM" not in titles


# ── fetch_jobs ───────────────────────────────────────────────────

def _make_config(**kwargs):
    return {"linkedin_email": kwargs, "search": {"max_age_days": 7}}


def test_fetch_jobs_raises_when_credentials_file_missing():
    config = _make_config(credentials_path="nonexistent.json", token_path="nonexistent_token.json")
    with pytest.raises(SourceNotConfiguredError, match="Gmail credentials not found"):
        fetch_jobs(config)


def test_fetch_jobs_raises_on_auth_failure(tmp_path):
    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    config = _make_config(credentials_path=str(creds), token_path=str(tmp_path / "token.json"))
    with patch("sources.linkedin_email._get_gmail_service", side_effect=Exception("auth error")):
        with pytest.raises(RuntimeError, match="Gmail API auth failed"):
            fetch_jobs(config)


def test_fetch_jobs_returns_empty_when_no_emails(tmp_path):
    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    config = _make_config(credentials_path=str(creds), token_path=str(tmp_path / "token.json"))

    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {"messages": []}

    with patch("sources.linkedin_email._get_gmail_service", return_value=mock_service):
        assert fetch_jobs(config) == []


def test_fetch_jobs_parses_email_html(tmp_path):
    creds = tmp_path / "creds.json"
    creds.write_text("{}")
    config = _make_config(credentials_path=str(creds), token_path=str(tmp_path / "token.json"))

    html = _alert_html([
        {"title": "Engineering Director", "url": "https://linkedin.com/jobs/view/1", "company": "Stripe"},
    ])
    encoded = base64.urlsafe_b64encode(html.encode()).decode()

    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {"messages": [{"id": "msg1"}]}
    mock_service.users().messages().get().execute.return_value = {
        "payload": {
            "mimeType": "text/html",
            "body": {"data": encoded},
            "parts": [],
            "headers": [{"name": "Date", "value": "Mon, 01 Jun 2025 12:00:00 +0000"}],
        }
    }

    with patch("sources.linkedin_email._get_gmail_service", return_value=mock_service):
        jobs = fetch_jobs(config)

    assert len(jobs) == 1
    assert jobs[0].title == "Engineering Director"
    assert jobs[0].source == "linkedin"
