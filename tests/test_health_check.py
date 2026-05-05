"""Unit tests for pipeline/health_check.py"""

from pipeline.health_check import HealthStatus, SourceNotConfiguredError, check_llm, status_emoji


def _make_config(api_key="sk-real-key"):
    return {"anthropic": {"api_key": api_key}}


# ── HealthStatus ─────────────────────────────────────────────────

def test_health_status_ok():
    h = HealthStatus(name="JSearch", ok=True)
    assert h.ok is True
    assert h.detail == ""

def test_health_status_failed():
    h = HealthStatus(name="Adzuna", ok=False, detail="429 Too Many Requests")
    assert h.ok is False
    assert h.detail == "429 Too Many Requests"


# ── check_llm ────────────────────────────────────────────────────

def test_check_llm_ok():
    h = check_llm(_make_config(api_key="sk-ant-real"))
    assert h.ok is True
    assert h.name == "LLM"

def test_check_llm_placeholder_key():
    h = check_llm(_make_config(api_key="YOUR_ANTHROPIC_KEY"))
    assert h.ok is False
    assert "not configured" in h.detail

def test_check_llm_empty_key():
    h = check_llm(_make_config(api_key=""))
    assert h.ok is False

def test_check_llm_missing_section():
    h = check_llm({})
    assert h.ok is False


# ── status_emoji ─────────────────────────────────────────────────

def test_status_emoji_ok():
    assert status_emoji(HealthStatus(name="X", ok=True, job_count=5)) == "✅"

def test_status_emoji_ok_no_job_count_sentinel():
    # job_count=-1 means "not a job source" (e.g. LLM) — must not trigger the zero-jobs warning
    assert status_emoji(HealthStatus(name="LLM", ok=True, job_count=-1)) == "✅"

def test_status_emoji_zero_jobs():
    assert status_emoji(HealthStatus(name="X", ok=True, job_count=0)) == "⚠️"

def test_status_emoji_error():
    assert status_emoji(HealthStatus(name="X", ok=False, detail="timeout")) == "❌"


# ── SourceNotConfiguredError ─────────────────────────────────────

def test_source_not_configured_error_is_exception():
    exc = SourceNotConfiguredError("Email credentials not configured")
    assert isinstance(exc, Exception)
    assert "Email" in str(exc)
