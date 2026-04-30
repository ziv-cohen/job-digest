"""Unit tests for pipeline/ignore_list.py"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pipeline.ignore_list import load, save, add_url, filter_jobs, _get_path


def _make_config(path: str = "ignored_jobs.json") -> dict:
    return {"pipeline": {"ignore_list_path": path}}


def _make_job(url: str) -> MagicMock:
    job = MagicMock()
    job.url = url
    return job


# ── load / save ──────────────────────────────────────────────────

def test_load_returns_empty_set_when_file_missing(tmp_path):
    assert load(tmp_path / "missing.json") == set()

def test_load_returns_urls_from_file(tmp_path):
    p = tmp_path / "ignored.json"
    p.write_text(json.dumps(["https://a.com", "https://b.com"]))
    assert load(p) == {"https://a.com", "https://b.com"}

def test_load_returns_empty_on_corrupt_file(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not json{{{")
    assert load(p) == set()

def test_save_writes_sorted_json(tmp_path):
    p = tmp_path / "out.json"
    save(p, {"https://z.com", "https://a.com"})
    data = json.loads(p.read_text())
    assert data == ["https://a.com", "https://z.com"]

def test_save_overwrites_existing(tmp_path):
    p = tmp_path / "out.json"
    save(p, {"https://old.com"})
    save(p, {"https://new.com"})
    assert json.loads(p.read_text()) == ["https://new.com"]


# ── add_url ──────────────────────────────────────────────────────

def test_add_url_creates_file_and_persists(tmp_path):
    config = _make_config(str(tmp_path / "ignored.json"))
    add_url(config, "https://example.com/job/1")
    assert "https://example.com/job/1" in load(_get_path(config))

def test_add_url_is_idempotent(tmp_path):
    config = _make_config(str(tmp_path / "ignored.json"))
    add_url(config, "https://example.com/job/1")
    add_url(config, "https://example.com/job/1")
    assert len(load(_get_path(config))) == 1

def test_add_url_appends_to_existing(tmp_path):
    config = _make_config(str(tmp_path / "ignored.json"))
    add_url(config, "https://example.com/job/1")
    add_url(config, "https://example.com/job/2")
    assert len(load(_get_path(config))) == 2


# ── filter_jobs ──────────────────────────────────────────────────

def test_filter_jobs_removes_ignored(tmp_path):
    config = _make_config(str(tmp_path / "ignored.json"))
    save(_get_path(config), {"https://example.com/job/1"})
    jobs = [_make_job("https://example.com/job/1"), _make_job("https://example.com/job/2")]
    kept, removed = filter_jobs(jobs, config)
    assert removed == 1
    assert len(kept) == 1
    assert kept[0].url == "https://example.com/job/2"

def test_filter_jobs_returns_all_when_list_empty(tmp_path):
    config = _make_config(str(tmp_path / "missing.json"))
    jobs = [_make_job("https://example.com/job/1")]
    kept, removed = filter_jobs(jobs, config)
    assert removed == 0
    assert kept == jobs

def test_filter_jobs_zero_removed_when_no_match(tmp_path):
    config = _make_config(str(tmp_path / "ignored.json"))
    save(_get_path(config), {"https://other.com/job/99"})
    jobs = [_make_job("https://example.com/job/1")]
    kept, removed = filter_jobs(jobs, config)
    assert removed == 0
    assert len(kept) == 1

def test_filter_jobs_respects_ignored_urls_from_config(tmp_path):
    config = _make_config(str(tmp_path / "missing.json"))
    config["pipeline"]["ignored_urls"] = ["https://example.com/job/1"]
    jobs = [_make_job("https://example.com/job/1"), _make_job("https://example.com/job/2")]
    kept, removed = filter_jobs(jobs, config)
    assert removed == 1
    assert kept[0].url == "https://example.com/job/2"

def test_filter_jobs_merges_file_and_env_sources(tmp_path):
    # The two ignore sources are independent and merged at filter time:
    # - save() writes job/1 to the on-disk JSON file (local --ignore flag source)
    # - config["pipeline"]["ignored_urls"] holds job/2 in memory (IGNORED_URLS env var source)
    # Neither overwrites the other; filter_jobs unions both sets.
    config = _make_config(str(tmp_path / "ignored.json"))
    save(_get_path(config), {"https://example.com/job/1"})
    config["pipeline"]["ignored_urls"] = ["https://example.com/job/2"]
    jobs = [_make_job("https://example.com/job/1"), _make_job("https://example.com/job/2"),
            _make_job("https://example.com/job/3")]
    kept, removed = filter_jobs(jobs, config)
    assert removed == 2
    assert kept[0].url == "https://example.com/job/3"
