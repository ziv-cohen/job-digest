"""Unit tests for sources/adzuna.py"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from pipeline.health_check import SourceNotConfiguredError
from sources.adzuna import fetch_jobs, _parse_job, _country_to_currency


def _item(**kwargs):
    """Build a minimal valid Adzuna API result item."""
    base = {
        "title": "Engineering Director",
        "company": {"display_name": "Stripe"},
        "redirect_url": "https://adzuna.com/job/123",
        "location": {"display_name": "London, UK"},
        "created": datetime.now(timezone.utc).isoformat(),
        "salary_min": 90000,
        "salary_max": 130000,
        "salary_is_predicted": 0,
        "contract_type": "permanent",
        "contract_time": "full_time",
        "description": "Lead our engineering org.",
    }
    base.update(kwargs)
    return base


def _make_config(app_id="test-id", app_key="test-key"):
    return {
        "api_keys": {"adzuna_app_id": app_id, "adzuna_app_key": app_key},
        "search": {
            "role_titles": ["engineering manager"],
            "max_age_days": 7,
        },
    }


# ── _country_to_currency ─────────────────────────────────────────

def test_currency_gb():
    assert _country_to_currency("gb") == "GBP"

def test_currency_de():
    assert _country_to_currency("de") == "EUR"

def test_currency_pl():
    assert _country_to_currency("pl") == "PLN"

def test_currency_unknown_defaults_eur():
    assert _country_to_currency("xx") == "EUR"


# ── _parse_job ───────────────────────────────────────────────────

def test_parse_job_valid():
    job = _parse_job(_item(), "gb")
    assert job is not None
    assert job.title == "Engineering Director"
    assert job.company == "Stripe"
    assert job.source == "adzuna"
    assert job.salary_currency == "GBP"

def test_parse_job_missing_title_returns_none():
    assert _parse_job(_item(title=""), "gb") is None

def test_parse_job_missing_url_returns_none():
    assert _parse_job(_item(redirect_url=""), "gb") is None

def test_parse_job_extracts_location():
    job = _parse_job(_item(location={"display_name": "Berlin, Germany"}), "de")
    assert "Berlin" in job.location

def test_parse_job_parses_date():
    posted = datetime(2025, 6, 1, tzinfo=timezone.utc)
    job = _parse_job(_item(created=posted.isoformat()), "de")
    assert job.date_posted == posted

def test_parse_job_predicted_salary_kept_with_flag():
    job = _parse_job(_item(salary_min=100000, salary_max=150000, salary_is_predicted=1), "gb")
    assert job.salary_min == 100000
    assert job.salary_max == 150000
    assert job.salary_is_estimated is True

def test_parse_job_actual_salary_not_flagged():
    job = _parse_job(_item(salary_min=100000, salary_max=150000, salary_is_predicted=0), "gb")
    assert job.salary_min == 100000
    assert job.salary_max == 150000
    assert job.salary_is_estimated is False

def test_parse_job_remote_detected_from_description():
    job = _parse_job(_item(description="This is a remote-first role"), "gb")
    assert job.is_remote is True

def test_parse_job_remote_region_is_emea_for_all_countries():
    job = _parse_job(_item(), "fr")
    assert job.remote_region == "EMEA"

def test_parse_job_non_dict_company_returns_empty_string():
    item = _item()
    item["company"] = "Stripe as string"
    job = _parse_job(item, "gb")
    assert job.company == ""


# ── fetch_jobs ───────────────────────────────────────────────────

def test_fetch_jobs_raises_when_api_key_not_configured():
    config = _make_config(app_id="YOUR_ADZUNA_APP_ID")
    with pytest.raises(SourceNotConfiguredError):
        fetch_jobs(config)


def test_fetch_jobs_returns_recent_jobs():
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    api_response = {"results": [_item(created=recent.isoformat())]}

    mock_resp = MagicMock()
    mock_resp.json.return_value = api_response
    mock_resp.raise_for_status.return_value = None

    with patch("sources.adzuna.requests.get", return_value=mock_resp):
        jobs = fetch_jobs(_make_config())

    assert len(jobs) > 0
    assert all(j.source == "adzuna" for j in jobs)


def test_fetch_jobs_filters_old_jobs():
    old = datetime.now(timezone.utc) - timedelta(days=10)
    api_response = {"results": [_item(created=old.isoformat())]}

    mock_resp = MagicMock()
    mock_resp.json.return_value = api_response
    mock_resp.raise_for_status.return_value = None

    with patch("sources.adzuna.requests.get", return_value=mock_resp):
        jobs = fetch_jobs(_make_config())

    assert jobs == []


def test_fetch_jobs_paginates_when_full_page_returned():
    # If a page returns exactly 50 results, the next page should be fetched.
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    full_page = {"results": [_item(created=recent.isoformat())] * 50}
    empty_page = {"results": []}

    mock_resp_full = MagicMock()
    mock_resp_full.json.return_value = full_page
    mock_resp_full.raise_for_status.return_value = None

    mock_resp_empty = MagicMock()
    mock_resp_empty.json.return_value = empty_page
    mock_resp_empty.raise_for_status.return_value = None

    # Config with a single country and single title to keep call count predictable
    config = _make_config()
    config["search"]["role_titles"] = ["engineering director"]

    with patch("sources.adzuna.COUNTRY_CODES", ["gb"]), \
         patch("sources.adzuna.requests.get", side_effect=[mock_resp_full, mock_resp_empty]) as mock_get:
        jobs = fetch_jobs(config)

    # Should have fetched page 1 (50 results) and page 2 (0 results → stop)
    urls_called = [c.args[0] for c in mock_get.call_args_list]
    assert any("/search/1" in u for u in urls_called)
    assert any("/search/2" in u for u in urls_called)
    assert len(jobs) == 50


def test_fetch_jobs_handles_request_error():
    import requests as req
    with patch("sources.adzuna.requests.get", side_effect=req.RequestException("timeout")):
        jobs = fetch_jobs(_make_config())
    assert jobs == []
