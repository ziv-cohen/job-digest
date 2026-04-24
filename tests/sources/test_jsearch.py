"""Unit tests for sources/jsearch.py"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from pipeline.health_check import SourceNotConfiguredError
from sources.jsearch import fetch_jobs, _parse_job, _infer_remote_region


def _item(**kwargs):
    """Build a minimal valid JSearch API result item."""
    base = {
        "job_title": "Engineering Director",
        "employer_name": "Acme Corp",
        "job_apply_link": "https://example.com/apply",
        "job_city": "Prague",
        "job_state": "",
        "job_country": "CZ",
        "job_is_remote": False,
        "job_posted_at_datetime_utc": datetime.now(timezone.utc).isoformat(),
        "job_min_salary": None,
        "job_max_salary": None,
        "job_salary_currency": "",
        "job_salary_period": "",
        "job_employment_type": "FULLTIME",
        "job_description": "Leading the engineering team.",
    }
    base.update(kwargs)
    return base


# ── _infer_remote_region ─────────────────────────────────────────

def test_infer_region_emea_europe():
    assert _infer_remote_region("Europe", True) == "EMEA"

def test_infer_region_emea_uk():
    assert _infer_remote_region("United Kingdom", True) == "EMEA"

def test_infer_region_worldwide():
    assert _infer_remote_region("Worldwide", True) == "Worldwide"

def test_infer_region_anywhere():
    assert _infer_remote_region("Anywhere", True) == "Worldwide"

def test_infer_region_not_remote():
    assert _infer_remote_region("Prague", False) == ""

def test_infer_region_unknown_location():
    assert _infer_remote_region("Unknown City", True) == ""


# ── _parse_job ───────────────────────────────────────────────────

def test_parse_job_valid_item():
    job = _parse_job(_item())
    assert job is not None
    assert job.title == "Engineering Director"
    assert job.company == "Acme Corp"
    assert job.source == "jsearch"

def test_parse_job_missing_title_returns_none():
    assert _parse_job(_item(job_title="")) is None

def test_parse_job_missing_company_returns_none():
    assert _parse_job(_item(employer_name="")) is None

def test_parse_job_parses_date():
    posted = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    job = _parse_job(_item(job_posted_at_datetime_utc=posted.isoformat()))
    assert job.date_posted == posted

def test_parse_job_invalid_date_leaves_none():
    job = _parse_job(_item(job_posted_at_datetime_utc="not-a-date"))
    assert job.date_posted is None

def test_parse_job_assembles_location():
    job = _parse_job(_item(job_city="Prague", job_state="", job_country="CZ"))
    assert "Prague" in job.location
    assert "CZ" in job.location

def test_parse_job_salary_fields():
    job = _parse_job(_item(job_min_salary=80000, job_max_salary=120000, job_salary_currency="EUR"))
    assert job.salary_min == 80000
    assert job.salary_max == 120000
    assert job.salary_currency == "EUR"

def test_parse_job_remote_flag():
    job = _parse_job(_item(job_is_remote=True, job_country="United Kingdom"))
    assert job.is_remote is True
    assert job.remote_region == "EMEA"

def test_parse_job_truncates_description():
    long_desc = "x" * 5000
    job = _parse_job(_item(job_description=long_desc))
    assert len(job.description) == 2000


# ── fetch_jobs ───────────────────────────────────────────────────

def _make_config(api_key="real-key"):
    return {
        "api_keys": {"jsearch_rapidapi_key": api_key},
        "search": {
            "role_titles": ["engineering manager"],
            "locations": {"primary_city": "Prague", "country": "Czech Republic", "region": "EMEA"},
            "max_age_days": 7,
        },
    }


def test_fetch_jobs_raises_when_api_key_not_configured():
    config = _make_config(api_key="YOUR_RAPIDAPI_KEY")
    with pytest.raises(SourceNotConfiguredError):
        fetch_jobs(config)


def test_fetch_jobs_returns_jobs_within_cutoff():
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    api_response = {"data": [_item(job_posted_at_datetime_utc=recent.isoformat())]}

    mock_resp = MagicMock()
    mock_resp.json.return_value = api_response
    mock_resp.raise_for_status.return_value = None

    with patch("sources.jsearch.requests.get", return_value=mock_resp):
        jobs = fetch_jobs(_make_config())

    assert len(jobs) > 0
    assert all(j.source == "jsearch" for j in jobs)


def test_fetch_jobs_filters_old_jobs():
    old = datetime.now(timezone.utc) - timedelta(days=10)
    api_response = {"data": [_item(job_posted_at_datetime_utc=old.isoformat())]}

    mock_resp = MagicMock()
    mock_resp.json.return_value = api_response
    mock_resp.raise_for_status.return_value = None

    with patch("sources.jsearch.requests.get", return_value=mock_resp):
        jobs = fetch_jobs(_make_config())

    assert jobs == []


def test_fetch_jobs_handles_request_error():
    import requests as req
    with patch("sources.jsearch.requests.get", side_effect=req.RequestException("timeout")):
        jobs = fetch_jobs(_make_config())
    assert jobs == []


def test_fetch_jobs_query_count_is_groups_times_two():
    # Titles are grouped in batches of 4; each group × 2 locations = total queries.
    config = _make_config()
    config["search"]["role_titles"] = ["em", "director", "vp", "cto", "head"]  # 5 titles → 2 groups

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": []}
    mock_resp.raise_for_status.return_value = None

    with patch("sources.jsearch.requests.get", return_value=mock_resp) as mock_get:
        fetch_jobs(config)

    assert mock_get.call_count == 4  # ceil(5/4)=2 groups × 2 locations


def test_fetch_jobs_or_groups_titles_correctly():
    # Each OR group contains up to 4 titles joined with OR.
    config = _make_config()
    # 5 titles → 2 groups: first 4, then 1
    config["search"]["role_titles"] = ["engineering manager", "engineering director", "vp engineering", "cto", "head of engineering"]

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": []}
    mock_resp.raise_for_status.return_value = None

    with patch("sources.jsearch.requests.get", return_value=mock_resp) as mock_get:
        fetch_jobs(config)

    queries = [c.kwargs["params"]["query"] for c in mock_get.call_args_list]
    # First group contains the first 4 titles joined with OR
    assert '"engineering manager" OR "engineering director" OR "vp engineering" OR "cto"' in queries[0]
    # Second group contains the remaining title
    assert '"head of engineering"' in queries[1]


def test_fetch_jobs_prague_and_emea_queries():
    # First query targets Prague, second targets EMEA remote.
    config = _make_config()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": []}
    mock_resp.raise_for_status.return_value = None

    with patch("sources.jsearch.requests.get", return_value=mock_resp) as mock_get:
        fetch_jobs(config)

    queries = [c.kwargs["params"]["query"] for c in mock_get.call_args_list]
    assert any("Prague" in q for q in queries)
    assert any("remote" in q for q in queries)


