"""Unit tests for sources/remotive.py"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from sources.remotive import fetch_jobs, _parse_job, _infer_region


def _item(**kwargs):
    base = {
        "title": "Engineering Manager",
        "company_name": "Remote Co",
        "url": "https://remotive.com/job/123",
        "candidate_required_location": "Europe",
        "publication_date": datetime.now(timezone.utc).isoformat(),
        "salary": "$120k–150k",
        "job_type": "full_time",
        "description": "<p>Lead our engineering team.</p>",
    }
    base.update(kwargs)
    return base


def _make_config():
    return {
        "search": {
            "role_titles": ["engineering manager", "engineering director"],
            "max_age_days": 7,
        },
    }


# ── _infer_region ────────────────────────────────────────────────

def test_infer_region_europe():
    assert _infer_region("Europe") == "EMEA"

def test_infer_region_uk():
    assert _infer_region("UK") == "EMEA"

def test_infer_region_czech():
    assert _infer_region("Czech Republic") == "EMEA"

def test_infer_region_worldwide():
    assert _infer_region("Worldwide") == "Worldwide"

def test_infer_region_anywhere():
    assert _infer_region("Anywhere") == "Worldwide"

def test_infer_region_empty_string():
    assert _infer_region("") == "Worldwide"

def test_infer_region_us_only():
    assert _infer_region("USA") == ""


# ── _parse_job ───────────────────────────────────────────────────

def test_parse_job_valid():
    job = _parse_job(_item())
    assert job is not None
    assert job.title == "Engineering Manager"
    assert job.company == "Remote Co"
    assert job.source == "remotive"
    assert job.is_remote is True

def test_parse_job_missing_title_returns_none():
    assert _parse_job(_item(title="")) is None

def test_parse_job_missing_company_returns_none():
    assert _parse_job(_item(company_name="")) is None

def test_parse_job_parses_iso_date():
    posted = datetime(2025, 6, 1, tzinfo=timezone.utc)
    job = _parse_job(_item(publication_date=posted.isoformat()))
    assert job.date_posted == posted

def test_parse_job_parses_alternative_date_format():
    job = _parse_job(_item(publication_date="2025-06-01T12:00:00"))
    assert job.date_posted is not None
    assert job.date_posted.year == 2025

def test_parse_job_invalid_date_leaves_none():
    job = _parse_job(_item(publication_date="not-a-date"))
    assert job.date_posted is None

def test_parse_job_region_inferred_from_location():
    job = _parse_job(_item(candidate_required_location="Europe"))
    assert job.remote_region == "EMEA"

def test_parse_job_salary_text_preserved():
    job = _parse_job(_item(salary="$100k–130k"))
    assert job.salary_text == "$100k–130k"

def test_parse_job_truncates_description():
    job = _parse_job(_item(description="x" * 5000))
    assert len(job.description) == 2000


# ── fetch_jobs ───────────────────────────────────────────────────

def test_fetch_jobs_filters_by_title():
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    api_response = {
        "jobs": [
            _item(title="Engineering Manager", publication_date=recent.isoformat()),
            _item(title="Sales Manager", publication_date=recent.isoformat()),
        ]
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = api_response
    mock_resp.raise_for_status.return_value = None

    with patch("sources.remotive.requests.get", return_value=mock_resp):
        jobs = fetch_jobs(_make_config())

    titles = [j.title for j in jobs]
    assert "Engineering Manager" in titles
    assert "Sales Manager" not in titles


def test_fetch_jobs_filters_old_jobs():
    old = datetime.now(timezone.utc) - timedelta(days=10)
    api_response = {"jobs": [_item(publication_date=old.isoformat())]}

    mock_resp = MagicMock()
    mock_resp.json.return_value = api_response
    mock_resp.raise_for_status.return_value = None

    with patch("sources.remotive.requests.get", return_value=mock_resp):
        jobs = fetch_jobs(_make_config())

    assert jobs == []


def test_fetch_jobs_handles_request_error():
    import requests as req
    with patch("sources.remotive.requests.get", side_effect=req.RequestException("timeout")):
        jobs = fetch_jobs(_make_config())
    assert jobs == []
