"""Unit tests for sources/startupjobs.py"""

from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup

from sources.startupjobs import fetch_jobs, _parse_card


def _make_card(title="Engineering Director", company="Startup s.r.o.",
               location="Prague, CZ", href="/en/offer/123", remote=False):
    """Build a minimal BeautifulSoup card element matching StartupJobs HTML."""
    remote_text = " remote" if remote else ""
    html = f"""
    <article>
      <h2><a href="{href}">{title}</a></h2>
      <span class="company">{company}</span>
      <span class="location">{location}{remote_text}</span>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")
    return soup.find("article")


def _make_config():
    return {
        "search": {
            "role_titles": ["engineering director", "engineering manager", "cto"],
            "max_age_days": 7,
        },
    }


# ── _parse_card ──────────────────────────────────────────────────

def test_parse_card_valid():
    card = _make_card()
    job = _parse_card(card, "engineering director")
    assert job is not None
    assert job.title == "Engineering Director"
    assert job.company == "Startup s.r.o."
    assert job.source == "startupjobs"

def test_parse_card_no_link_returns_none():
    soup = BeautifulSoup("<article><p>No link here</p></article>", "html.parser")
    card = soup.find("article")
    assert _parse_card(card, "query") is None

def test_parse_card_sets_relative_href_to_absolute():
    card = _make_card(href="/en/offer/456")
    job = _parse_card(card, "query")
    assert job.url.startswith("http")

def test_parse_card_keeps_absolute_href():
    card = _make_card(href="https://www.startupjobs.cz/en/offer/456")
    job = _parse_card(card, "query")
    assert job.url == "https://www.startupjobs.cz/en/offer/456"

def test_parse_card_remote_detection():
    card = _make_card(remote=True)
    job = _parse_card(card, "query")
    assert job.is_remote is True
    assert job.remote_region == "EMEA"

def test_parse_card_not_remote():
    card = _make_card(remote=False)
    job = _parse_card(card, "query")
    assert job.is_remote is False

def test_parse_card_company_type_is_product():
    card = _make_card()
    job = _parse_card(card, "query")
    assert job.company_type == "product"

def test_parse_card_has_date():
    card = _make_card()
    job = _parse_card(card, "query")
    assert job.date_posted is not None


# ── fetch_jobs ───────────────────────────────────────────────────

def test_fetch_jobs_deduplicates_by_url():
    card_html = """
    <html><body>
      <article>
        <h2><a href="/en/offer/1">Engineering Director</a></h2>
        <span class="company">Acme</span>
      </article>
    </body></html>
    """
    mock_resp = MagicMock()
    mock_resp.text = card_html
    mock_resp.raise_for_status.return_value = None

    with patch("sources.startupjobs.requests.get", return_value=mock_resp):
        jobs = fetch_jobs(_make_config())

    urls = [j.url for j in jobs]
    assert len(urls) == len(set(urls))


def test_fetch_jobs_handles_request_error():
    import requests as req
    with patch("sources.startupjobs.requests.get", side_effect=req.RequestException("timeout")):
        jobs = fetch_jobs(_make_config())
    assert jobs == []
