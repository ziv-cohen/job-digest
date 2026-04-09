"""Unit tests for sources/startupjobs.py"""

import requests as req
from unittest.mock import MagicMock, patch

from sources.startupjobs import fetch_jobs, _parse_item, _parse_salary, _parse_location


def _make_config():
    return {"search": {"max_age_days": 7}}


def _make_item(**overrides) -> dict:
    base = {
        "id": 1,
        "name": "Engineering Director",
        "url": "/nabidka/1/engineering-director",
        "company": "Startup s.r.o.",
        "companyType": "start",
        "locations": "Praha",
        "isRemote": False,
        "salary": None,
        "description": "<p>Great role</p>",
        "isStartup": True,
    }
    return {**base, **overrides}


def _make_api_response(items: list[dict], page: int = 1, max_pages: int = 1) -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = {
        "resultSet": items,
        "resultCount": len(items),
        "paginator": {"current": page, "max": max_pages},
    }
    return mock


# ── _parse_salary ────────────────────────────────────────────────

def test_parse_salary_monthly_converts_to_annual():
    sal_min, sal_max, cur = _parse_salary({"min": 100000, "max": 150000, "measure": "monthly", "currency": "CZK"})
    assert sal_min == 1200000
    assert sal_max == 1800000
    assert cur == "CZK"

def test_parse_salary_yearly_unchanged():
    sal_min, sal_max, cur = _parse_salary({"min": 100000, "max": 150000, "measure": "yearly", "currency": "EUR"})
    assert sal_min == 100000
    assert sal_max == 150000

def test_parse_salary_none_returns_empty():
    assert _parse_salary(None) == (None, None, "")

def test_parse_salary_missing_min():
    sal_min, sal_max, cur = _parse_salary({"min": None, "max": 120000, "measure": "monthly", "currency": "CZK"})
    assert sal_min is None
    assert sal_max == 1440000


# ── _parse_location ───────────────────────────────────────────────

def test_parse_location_praha_normalised():
    assert _parse_location({"locations": "Praha", "isRemote": False}) == "Prague, CZ"

def test_parse_location_other_city():
    assert _parse_location({"locations": "Brno", "isRemote": False}) == "Brno, CZ"

def test_parse_location_remote_returns_empty():
    assert _parse_location({"locations": "Praha", "isRemote": True}) == ""

def test_parse_location_empty():
    assert _parse_location({"locations": "", "isRemote": False}) == ""


# ── _parse_item ──────────────────────────────────────────────────

def test_parse_item_basic_fields(freeze_now=None):
    from datetime import timezone
    item = _make_item()
    job = _parse_item(item, cutoff=__import__('datetime').datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert job is not None
    assert job.title == "Engineering Director"
    assert job.company == "Startup s.r.o."
    assert job.source == "startupjobs"
    assert job.url == "https://www.startupjobs.cz/nabidka/1/engineering-director"
    assert job.company_type == "product"

def test_parse_item_absolute_url_kept():
    item = _make_item(url="https://www.startupjobs.cz/nabidka/1/test")
    from datetime import timezone
    job = _parse_item(item, cutoff=__import__('datetime').datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert job.url == "https://www.startupjobs.cz/nabidka/1/test"

def test_parse_item_remote():
    from datetime import timezone
    item = _make_item(isRemote=True)
    job = _parse_item(item, cutoff=__import__('datetime').datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert job.is_remote is True
    assert job.remote_region == "EMEA"

def test_parse_item_with_salary():
    from datetime import timezone
    item = _make_item(salary={"min": 100000, "max": 150000, "measure": "monthly", "currency": "CZK"})
    job = _parse_item(item, cutoff=__import__('datetime').datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert job.salary_min == 1200000
    assert job.salary_max == 1800000
    assert job.salary_currency == "CZK"

def test_parse_item_missing_title_returns_none():
    from datetime import timezone
    item = _make_item(name="")
    job = _parse_item(item, cutoff=__import__('datetime').datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert job is None

def test_parse_item_irrelevant_title_filtered_out():
    from datetime import timezone
    item = _make_item(name="Head of Sales (hands-on) - B2B SaaS")
    job = _parse_item(item, cutoff=__import__('datetime').datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert job is None

def test_parse_item_cto_title_passes():
    from datetime import timezone
    item = _make_item(name="CTO / Co-Founder")
    job = _parse_item(item, cutoff=__import__('datetime').datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert job is not None


# ── fetch_jobs ───────────────────────────────────────────────────

def test_fetch_jobs_returns_jobs():
    mock_resp = _make_api_response([_make_item(), _make_item(id=2, name="CTO")])
    with patch("sources.startupjobs.requests.get", return_value=mock_resp):
        jobs = fetch_jobs(_make_config())
    assert len(jobs) > 0

def test_fetch_jobs_deduplicates_across_queries():
    item = _make_item()
    mock_resp = _make_api_response([item])
    with patch("sources.startupjobs.requests.get", return_value=mock_resp):
        jobs = fetch_jobs(_make_config())
    # Same item returned for all queries — should appear only once
    assert len(jobs) == 1

def test_fetch_jobs_handles_request_error():
    with patch("sources.startupjobs.requests.get", side_effect=req.RequestException("timeout")):
        jobs = fetch_jobs(_make_config())
    assert jobs == []

def test_fetch_jobs_stops_at_last_page():
    # Page 1 has results, page 2 should not be fetched (max=1)
    mock_resp = _make_api_response([_make_item()], page=1, max_pages=1)
    with patch("sources.startupjobs.requests.get", return_value=mock_resp) as mock_get:
        fetch_jobs(_make_config())
    # Each query makes exactly 1 call (no page 2)
    calls_per_query = [c for c in mock_get.call_args_list if c.kwargs.get("params", {}).get("page") == 1]
    assert len(calls_per_query) == len(__import__('sources.startupjobs', fromlist=['_SEARCH_QUERIES'])._SEARCH_QUERIES)
