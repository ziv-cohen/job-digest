"""Unit tests for output/telegram_digest.py"""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from models import Job
from output.telegram_digest import send_digest, _build_messages, _format_job
from pipeline.health_check import HealthStatus


_WEIGHTS = {
    "profile_match": 45,
    "title": 15,
    "location": 15,
    "company_type": 10,
    "seniority": 5,
    "freshness": 5,
    "conditions": 5,
}


def make_job(**kwargs) -> Job:
    defaults = dict(
        title="Engineering Director",
        company="Acme",
        url="https://example.com/job/1",
        source="jsearch",
        score=75.0,
        score_breakdown={
            "profile_match": 80.0,
            "title": 100.0,
            "location": 100.0,
            "company_type": 100.0,
            "seniority": 100.0,
            "freshness": 70.0,
            "conditions": 0.0,
        },
        date_posted=datetime.now(timezone.utc) - timedelta(hours=2),
        has_growth_signals=False,
    )
    return Job(**{**defaults, **kwargs})


def _make_config(bot_token="123:ABC", chat_id="456"):
    return {
        "telegram": {"bot_token": bot_token, "chat_id": chat_id},
        "scoring": {"weights": _WEIGHTS},
    }


# ── _format_job ──────────────────────────────────────────────────

def test_format_job_contains_title():
    job = make_job()
    result = _format_job(1, job)
    assert "Engineering Director" in result

def test_format_job_contains_score():
    job = make_job(score=75.0)
    result = _format_job(1, job)
    assert "75%" in result

def test_format_job_contains_url():
    job = make_job(url="https://example.com/apply")
    result = _format_job(1, job)
    assert "https://example.com/apply" in result

def test_format_job_remote_region_shown():
    job = make_job(is_remote=True, remote_region="EMEA")
    result = _format_job(1, job)
    assert "Remote" in result
    assert "EMEA" in result

def test_format_job_growth_signals_shown():
    job = make_job(has_growth_signals=True)
    result = _format_job(1, job)
    assert "Growing company" in result

def test_format_job_growth_signals_hidden_when_false():
    job = make_job(has_growth_signals=False)
    result = _format_job(1, job)
    assert "Growing company" not in result

def test_format_job_salary_disclosed():
    job = make_job(salary_text="€120k–150k")
    result = _format_job(1, job)
    assert "€120k–150k" in result

def test_format_job_salary_not_disclosed():
    job = make_job(salary_text="", salary_min=None, salary_max=None)
    result = _format_job(1, job)
    assert "Not disclosed" in result

def test_format_job_breakdown_line_shown():
    job = make_job()
    result = _format_job(1, job)
    assert "📊" in result
    assert "🤖 Profile match 80" in result
    assert "📌 Title 100" in result

def test_format_job_breakdown_omits_zero_score():
    # conditions score=0 → 💼 omitted from breakdown line
    job = make_job()
    result = _format_job(1, job)
    assert "💼" not in result

def test_format_job_rationale_shown_when_present():
    job = make_job(profile_match_rationale="Strong Director match, EMEA remote")
    result = _format_job(1, job)
    assert "🤖" in result
    assert "Strong Director match" in result

def test_format_job_rationale_hidden_when_empty():
    job = make_job(profile_match_rationale="")
    result = _format_job(1, job)
    # breakdown uses "🤖80" (no space); rationale line uses "🤖 text" (with space)
    assert "\n🤖 " not in result

def test_format_job_today_label():
    job = make_job(date_posted=datetime.now(timezone.utc) - timedelta(hours=1))
    result = _format_job(1, job)
    assert "Today" in result

def test_format_job_yesterday_label():
    job = make_job(date_posted=datetime.now(timezone.utc) - timedelta(hours=30))
    result = _format_job(1, job)
    assert "Yesterday" in result


# ── Health footer ────────────────────────────────────────────────

def test_build_messages_health_footer_shown():
    jobs = [make_job()]
    health = [HealthStatus("JSearch", ok=True), HealthStatus("LLM", ok=False, detail="no key")]
    messages = _build_messages(jobs, health=health)
    last = messages[-1]
    assert "🏥" in last
    assert "✅ JSearch" in last
    assert "❌ LLM (no key)" in last

def test_build_messages_no_health_footer_when_empty():
    jobs = [make_job()]
    messages = _build_messages(jobs, health=[])
    assert "🏥" not in messages[-1]

def test_build_messages_health_footer_omits_detail_when_ok():
    jobs = [make_job()]
    health = [HealthStatus("Adzuna", ok=True)]
    messages = _build_messages(jobs, health=health)
    assert "✅ Adzuna" in messages[-1]
    assert "(" not in messages[-1].split("🏥")[1]

def test_build_messages_health_footer_shows_job_count():
    jobs = [make_job()]
    health = [HealthStatus("JSearch", ok=True, job_count=42)]
    messages = _build_messages(jobs, health=health)
    assert "✅ JSearch (42)" in messages[-1]

def test_build_messages_health_footer_no_count_for_llm():
    jobs = [make_job()]
    health = [HealthStatus("LLM", ok=True)]  # job_count defaults to -1
    messages = _build_messages(jobs, health=health)
    assert "✅ LLM" in messages[-1]
    assert "(-1)" not in messages[-1]


# ── _build_messages ──────────────────────────────────────────────

def test_build_messages_returns_at_least_one():
    jobs = [make_job()]
    messages = _build_messages(jobs)
    assert len(messages) >= 1

def test_build_messages_header_in_first():
    jobs = [make_job()]
    messages = _build_messages(jobs)
    assert "Job Digest" in messages[0]

def test_build_messages_weights_shown_one_per_line():
    jobs = [make_job()]
    messages = _build_messages(jobs, weights=_WEIGHTS)
    header = messages[0]
    assert "🤖 Profile match 45%" in header
    assert "📌 Title 15%" in header
    assert "📍 Location 15%" in header
    assert "🏢 Company type 10%" in header
    assert "🏷 Seniority 5%" in header
    assert "🕐 Freshness 5%" in header
    assert "💼 Conditions 5%" in header
    # Each criterion on its own line
    assert "Profile match 45%\n📌" in header

def test_build_messages_zero_weight_omitted():
    jobs = [make_job()]
    weights = {**_WEIGHTS, "conditions": 0}
    messages = _build_messages(jobs, weights=weights)
    assert "💼" not in messages[0]

def test_build_messages_splits_when_over_limit():
    # Create enough jobs to exceed 4096 chars
    jobs = [make_job(title=f"Engineering Director {i}", description="x" * 100) for i in range(30)]
    messages = _build_messages(jobs)
    assert all(len(m) <= 4096 for m in messages)
    assert len(messages) > 1

def test_build_messages_all_jobs_present():
    jobs = [make_job(title=f"Role {i}") for i in range(5)]
    messages = _build_messages(jobs)
    combined = "".join(messages)
    for i in range(5):
        assert f"Role {i}" in combined


# ── send_digest ──────────────────────────────────────────────────

def test_send_digest_skips_missing_token():
    config = _make_config(bot_token="YOUR_TOKEN")
    assert send_digest([make_job()], config) is False

def test_send_digest_skips_missing_chat_id():
    config = _make_config(chat_id="")
    assert send_digest([make_job()], config) is False

def test_send_digest_skips_empty_jobs():
    config = _make_config()
    assert send_digest([], config) is True

def test_send_digest_posts_to_telegram():
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None

    with patch("output.telegram_digest.requests.post", return_value=mock_resp) as mock_post:
        result = send_digest([make_job()], _make_config())

    assert result is True
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"]["chat_id"] == "456"
    assert call_kwargs["json"]["parse_mode"] == "HTML"

def test_send_digest_returns_false_on_request_error():
    import requests as req
    with patch("output.telegram_digest.requests.post", side_effect=req.RequestException("timeout")):
        result = send_digest([make_job()], _make_config())
    assert result is False

def test_send_digest_missing_telegram_config():
    config = {}  # no "telegram" key at all
    assert send_digest([make_job()], config) is False
