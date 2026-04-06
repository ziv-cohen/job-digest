"""Unit tests for pipeline/deduplicator.py"""

from datetime import datetime

from models import Job
from pipeline.deduplicator import (
    deduplicate,
    _normalise,
    _make_dedup_key,
    _find_fuzzy_match,
    TITLE_SIMILARITY_THRESHOLD,
    COMPANY_SIMILARITY_MIN,
    COMPANY_SIMILARITY_SUBSTRING,
)


def make_job(**kwargs) -> Job:
    defaults = dict(title="Engineering Manager", company="Acme", url="https://example.com", source="jsearch")
    return Job(**{**defaults, **kwargs})


# ── _normalise ───────────────────────────────────────────────────

def test_normalise_lowercases():
    assert _normalise("Engineering Manager") == "engineering manager"

def test_normalise_strips_punctuation():
    assert _normalise("Sr. Engineering Manager!") == "sr engineering manager"

def test_normalise_collapses_whitespace():
    assert _normalise("  head   of   engineering  ") == "head of engineering"

def test_normalise_handles_empty():
    assert _normalise("") == ""


# ── _make_dedup_key ──────────────────────────────────────────────

def test_make_dedup_key_format():
    job = make_job(title="Engineering Director", company="Stripe")
    key = _make_dedup_key(job)
    assert "||" in key
    title_part, company_part = key.split("||")
    assert title_part == "engineering director"
    assert company_part == "stripe"


# ── _find_fuzzy_match ────────────────────────────────────────────

def test_find_fuzzy_match_identical():
    existing = {"engineering director||stripe": []}
    result = _find_fuzzy_match("engineering director||stripe", existing)
    assert result == "engineering director||stripe"

def test_find_fuzzy_match_minor_title_variation():
    # "Sr Engineering Director" vs "Senior Engineering Director" — should match
    existing = {"senior engineering director||acme": []}
    result = _find_fuzzy_match("sr engineering director||acme", existing)
    assert result == "senior engineering director||acme"

def test_find_fuzzy_match_different_company_no_match():
    existing = {"engineering director||stripe": []}
    result = _find_fuzzy_match("engineering director||google", existing)
    assert result is None

def test_find_fuzzy_match_title_substring():
    # "Engineering Director" is contained in "Engineering Director - Data Platform"
    existing = {"engineering director  data platform||acme": []}
    result = _find_fuzzy_match("engineering director||acme", existing)
    assert result == "engineering director  data platform||acme"

def test_find_fuzzy_match_title_substring_weak_company_no_match():
    # Substring match should NOT fire if company similarity is below COMPANY_SIMILARITY_SUBSTRING
    existing = {"engineering director  data platform||acme corp": []}
    result = _find_fuzzy_match("engineering director||totally different", existing)
    assert result is None

def test_find_fuzzy_match_completely_different():
    existing = {"product manager||spotify": []}
    result = _find_fuzzy_match("engineering director||stripe", existing)
    assert result is None

def test_find_fuzzy_match_empty_existing():
    result = _find_fuzzy_match("engineering director||stripe", {})
    assert result is None


# ── deduplicate ──────────────────────────────────────────────────

def test_deduplicate_removes_exact_duplicate():
    jobs = [
        make_job(title="Engineering Director", company="Stripe", source="jsearch"),
        make_job(title="Engineering Director", company="Stripe", source="adzuna"),
    ]
    result = deduplicate(jobs)
    assert len(result) == 1

def test_deduplicate_keeps_higher_priority_source():
    jobs = [
        make_job(title="Engineering Director", company="Stripe", source="adzuna"),
        make_job(title="Engineering Director", company="Stripe", source="jsearch"),
    ]
    result = deduplicate(jobs)
    assert result[0].source == "jsearch"

def test_deduplicate_merges_salary_from_duplicate():
    jobs = [
        make_job(title="Engineering Director", company="Stripe", source="jsearch", salary_text=""),
        make_job(title="Engineering Director", company="Stripe", source="adzuna", salary_text="€120k–150k"),
    ]
    result = deduplicate(jobs)
    assert result[0].salary_text == "€120k–150k"

def test_deduplicate_preserves_distinct_jobs():
    jobs = [
        make_job(title="Engineering Director", company="Stripe", source="jsearch"),
        make_job(title="Engineering Manager", company="Spotify", source="adzuna"),
    ]
    result = deduplicate(jobs)
    assert len(result) == 2

def test_deduplicate_handles_empty_input():
    assert deduplicate([]) == []

def test_deduplicate_handles_single_job():
    jobs = [make_job()]
    result = deduplicate(jobs)
    assert len(result) == 1

def test_deduplicate_subtitle_variation_is_duplicate():
    # "Engineering Director" vs "Engineering Director - Platform" at same company
    jobs = [
        make_job(title="Engineering Director", company="Acme", source="jsearch"),
        make_job(title="Engineering Director - Platform", company="Acme", source="remotive"),
    ]
    result = deduplicate(jobs)
    assert len(result) == 1
    assert result[0].source == "jsearch"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
