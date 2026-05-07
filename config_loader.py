"""Load and merge configuration from config.yaml and config.local.yaml."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml


def _write_file_from_env(env_var: str, file_path: str | None) -> None:
    """Write env var content to file_path if the env var is set and the file doesn't exist yet."""
    content = os.environ.get(env_var)
    if content and file_path and not os.path.exists(file_path):
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (override wins)."""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_dir: str | Path | None = None) -> dict[str, Any]:
    """Return the merged configuration dictionary.

    Resolution order (later wins):
      1. config.yaml          — defaults + structure
      2. config.local.yaml    — user secrets (gitignored)
      3. Environment variables — CI / container overrides
    """
    if config_dir is None:
        config_dir = Path(__file__).resolve().parent
    else:
        config_dir = Path(config_dir)

    # 1. Base config
    base_path = config_dir / "config.yaml"
    if not base_path.exists():
        raise FileNotFoundError(f"Base config not found: {base_path}")
    with open(base_path) as f:
        config = yaml.safe_load(f) or {}

    # 2. Local overrides (secrets)
    local_path = config_dir / "config.local.yaml"
    if local_path.exists():
        with open(local_path) as f:
            local = yaml.safe_load(f) or {}
        config = _deep_merge(config, local)

    # 3. Environment variable overrides
    env_map = {
        "JSEARCH_API_KEY": ("api_keys", "jsearch_rapidapi_key"),
        "ADZUNA_APP_ID": ("api_keys", "adzuna_app_id"),
        "ADZUNA_APP_KEY": ("api_keys", "adzuna_app_key"),
        "TELEGRAM_BOT_TOKEN": ("telegram", "bot_token"),
        "TELEGRAM_CHAT_ID": ("telegram", "chat_id"),
        "SMTP_SERVER": ("email", "smtp_server"),
        "SMTP_PORT": ("email", "smtp_port"),
        "SENDER_EMAIL": ("email", "sender_email"),
        "SENDER_PASSWORD": ("email", "sender_password"),
        "RECIPIENT_EMAIL": ("email", "recipient_email"),
        "ANTHROPIC_API_KEY": ("anthropic", "api_key"),
        "PROFILE_SUMMARY": ("profile_matcher", "profile_summary"),
        "PROFILE_MATCH_CACHE_PATH": ("profile_matcher", "cache_path"),
        "DIGEST_TIMEZONE": ("output", "timezone"),
        "IGNORE_LIST_PATH": ("pipeline", "ignore_list_path"),
        "GMAIL_CREDENTIALS_PATH": ("linkedin_email", "credentials_path"),
        "GMAIL_TOKEN_PATH": ("linkedin_email", "token_path"),
    }
    for env_var, path in env_map.items():
        value = os.environ.get(env_var)
        if value is not None:
            node = config
            for part in path[:-1]:
                node = node.setdefault(part, {})
            node[path[-1]] = int(value) if value.isdigit() else value

    # Parse IGNORED_URLS env var (JSON array) — primary ignore mechanism on Railway
    ignored_urls_raw = os.environ.get("IGNORED_URLS")
    if ignored_urls_raw:
        try:
            config.setdefault("pipeline", {})["ignored_urls"] = json.loads(ignored_urls_raw)
        except json.JSONDecodeError as exc:
            import logging
            logging.getLogger(__name__).warning("IGNORED_URLS env var is not valid JSON, ignoring: %s", exc)

    # Write Gmail credential files from env vars if provided (Railway deployment)
    # GMAIL_CREDENTIALS_JSON / GMAIL_TOKEN_JSON let you store file contents as env vars
    # instead of uploading files to a volume manually. Written once; token is refreshed in place.
    _write_file_from_env("GMAIL_CREDENTIALS_JSON", config.get("linkedin_email", {}).get("credentials_path"))
    _write_file_from_env("GMAIL_TOKEN_JSON", config.get("linkedin_email", {}).get("token_path"))

    # Validate scoring weights sum to 100
    weights = config.get("scoring", {}).get("weights", {})
    if weights:
        total = sum(weights.values())
        if total != 100:
            raise ValueError(f"Scoring weights must sum to 100, got {total}: {weights}")

    return config
