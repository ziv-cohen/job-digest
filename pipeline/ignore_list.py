"""Persistent ignore list — URLs of jobs the user has dismissed."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = "ignored_jobs.json"


def load(path: Path) -> set[str]:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as exc:
            logger.warning("Could not load ignore list: %s", exc)
    return set()


def save(path: Path, urls: set[str]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sorted(urls), f, indent=2)
    except Exception as exc:
        logger.warning("Could not save ignore list: %s", exc)


def add_url(config: dict, url: str) -> None:
    """Append a URL to the ignore list and persist it."""
    path = _get_path(config)
    urls = load(path)
    if url in urls:
        logger.info("Already in ignore list: %s", url)
        return
    urls.add(url)
    save(path, urls)
    logger.info("Added to ignore list (%d total): %s", len(urls), url)


def filter_jobs(jobs: list, config: dict) -> tuple[list, int]:
    """Remove ignored jobs. Returns (filtered_jobs, removed_count).

    Ignored URLs come from two sources (union):
    - ignored_jobs.json (local file, managed via --ignore flag)
    - IGNORED_URLS env var (JSON array, managed via Railway dashboard)

    Matching is prefix-based: an ignored entry matches any job URL that starts
    with it. Store just the base URL (no query params) to ignore all variants.
    """
    path = _get_path(config)
    from_file = load(path)
    from_env = set(config.get("pipeline", {}).get("ignored_urls", []))
    ignored = from_file | from_env
    logger.info("Ignore list: %d URL(s) loaded (%d from file, %d from env var)",
                len(ignored), len(from_file), len(from_env))
    if not ignored:
        return jobs, 0
    before = len(jobs)
    kept = [j for j in jobs if not any(j.url.startswith(prefix) for prefix in ignored)]
    return kept, before - len(kept)


def _get_path(config: dict) -> Path:
    return Path(config.get("pipeline", {}).get("ignore_list_path", _DEFAULT_PATH))
