"""Unit tests for pipeline/profile_matcher.py"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

from models import Job
from pipeline.profile_matcher import match_profile, _call_api


def make_job(**kwargs) -> Job:
    defaults = dict(
        title="Engineering Director",
        company="Acme",
        url="https://example.com/job/1",
        source="jsearch",
        score_breakdown={
            "profile_match": 0.0,
            "title": 100.0,
            "location": 100.0,
            "company_type": 100.0,
            "seniority": 100.0,
            "freshness": 100.0,
            "conditions": 0.0,
        },
    )
    return Job(**{**defaults, **kwargs})


def make_config(api_key="sk-test", profile_summary="Senior EM with 20 years exp"):
    return {
        "anthropic": {
            "api_key": api_key,
            "model": "claude-haiku-4-5-20251001",
        },
        "profile_matcher": {
            "profile_summary": profile_summary,
            "cache_path": "profile_match_cache.json",
            "fallback_score": 50,
        },
        "scoring": {
            "weights": {
                "profile_match": 45,
                "title": 15,
                "location": 15,
                "company_type": 10,
                "seniority": 5,
                "freshness": 5,
                "conditions": 5,
            },
        },
    }


def make_api_response(score: int, rationale: str) -> MagicMock:
    message = MagicMock()
    message.content[0].text = json.dumps({"score": score, "rationale": rationale})
    return message


# ── Graceful degradation ─────────────────────────────────────────

def test_no_api_key_sets_fallback_score():
    config = make_config(api_key="YOUR_ANTHROPIC_KEY")
    jobs = [make_job()]
    match_profile(jobs, config)
    assert jobs[0].score_breakdown["profile_match"] == 50.0

def test_no_profile_summary_sets_fallback_score():
    config = make_config(profile_summary="YOUR_PROFILE_SUMMARY")
    jobs = [make_job()]
    match_profile(jobs, config)
    assert jobs[0].score_breakdown["profile_match"] == 50.0

def test_fallback_does_not_recompute_total():
    config = make_config(api_key="YOUR_ANTHROPIC_KEY")
    job = make_job()
    original_score = job.score
    match_profile([job], config)
    assert job.score == original_score  # score untouched — score_jobs() computes weighted total


# ── Cache behaviour ──────────────────────────────────────────────

def test_cache_hit_skips_api_call(tmp_path):
    cache_data = {
        "https://example.com/job/1": {
            "score": 85,
            "rationale": "Great match",
            "model": "claude-haiku-4-5-20251001",
            "cached_at": "2025-01-01T00:00:00+00:00",
        }
    }
    cache_file = tmp_path / "cache.json"
    cache_file.write_text(json.dumps(cache_data))

    config = make_config()
    config["profile_matcher"]["cache_path"] = str(cache_file)

    jobs = [make_job()]
    mock_client = MagicMock()
    with patch("pipeline.profile_matcher._make_client", return_value=mock_client):
        match_profile(jobs, config)
        mock_client.messages.create.assert_not_called()

    assert jobs[0].score_breakdown["profile_match"] == 85.0
    assert jobs[0].profile_match_rationale == "Great match"

def test_cache_miss_calls_api_and_saves(tmp_path):
    cache_file = tmp_path / "cache.json"
    config = make_config()
    config["profile_matcher"]["cache_path"] = str(cache_file)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = make_api_response(78, "Good fit for Director role")

    jobs = [make_job()]
    with patch("pipeline.profile_matcher._make_client", return_value=mock_client):
        match_profile(jobs, config)

    assert jobs[0].score_breakdown["profile_match"] == 78.0
    assert jobs[0].profile_match_rationale == "Good fit for Director role"
    assert cache_file.exists()
    saved = json.loads(cache_file.read_text())
    assert "https://example.com/job/1" in saved
    assert saved["https://example.com/job/1"]["score"] == 78

def test_second_job_uses_cache_first_calls_api(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache_data = {
        "https://example.com/job/1": {"score": 85, "rationale": "Cached", "model": "x", "cached_at": ""},
    }
    cache_file.write_text(json.dumps(cache_data))

    config = make_config()
    config["profile_matcher"]["cache_path"] = str(cache_file)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = make_api_response(60, "Decent match")

    job1 = make_job(url="https://example.com/job/1")
    job2 = make_job(url="https://example.com/job/2")

    with patch("pipeline.profile_matcher._make_client", return_value=mock_client):
        match_profile([job1, job2], config)

    mock_client.messages.create.assert_called_once()  # only job2 hit the API
    assert job1.score_breakdown["profile_match"] == 85.0
    assert job2.score_breakdown["profile_match"] == 60.0


# ── _call_api ────────────────────────────────────────────────────

def test_call_api_returns_score_and_rationale():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = make_api_response(82, "Strong Director match")
    job = make_job()
    score, rationale = _call_api(mock_client, "claude-haiku-4-5-20251001", "My profile", job, 50)
    assert score == 82
    assert rationale == "Strong Director match"

def test_call_api_clamps_score_above_100():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = make_api_response(150, "Too high")
    job = make_job()
    score, _ = _call_api(mock_client, "claude-haiku-4-5-20251001", "My profile", job)
    assert score == 100

def test_call_api_clamps_score_below_zero():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = make_api_response(-10, "Too low")
    job = make_job()
    score, _ = _call_api(mock_client, "claude-haiku-4-5-20251001", "My profile", job)
    assert score == 0

def test_call_api_defaults_to_neutral_on_error():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API timeout")
    job = make_job()
    score, rationale = _call_api(mock_client, "claude-haiku-4-5-20251001", "My profile", job, 50)
    assert score == 50
    assert rationale == ""

def test_call_api_defaults_to_neutral_on_invalid_json():
    mock_client = MagicMock()
    mock_client.messages.create.return_value.content[0].text = "not json"
    job = make_job()
    score, rationale = _call_api(mock_client, "claude-haiku-4-5-20251001", "My profile", job, 50)
    assert score == 50
    assert rationale == ""


# ── Breakdown mutation ───────────────────────────────────────────

def test_match_profile_sets_breakdown_score(tmp_path):
    cache_file = tmp_path / "cache.json"
    config = make_config()
    config["profile_matcher"]["cache_path"] = str(cache_file)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = make_api_response(80, "Good match")

    job = make_job()
    with patch("pipeline.profile_matcher._make_client", return_value=mock_client):
        match_profile([job], config)

    assert job.score_breakdown["profile_match"] == 80.0
    assert job.profile_match_rationale == "Good match"

def test_profile_match_zero_sets_breakdown(tmp_path):
    cache_file = tmp_path / "cache.json"
    config = make_config()
    config["profile_matcher"]["cache_path"] = str(cache_file)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = make_api_response(0, "Wrong domain")

    job = make_job()
    with patch("pipeline.profile_matcher._make_client", return_value=mock_client):
        match_profile([job], config)

    assert job.score_breakdown["profile_match"] == 0.0
    assert job.profile_match_rationale == "Wrong domain"
