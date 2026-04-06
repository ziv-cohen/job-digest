"""Unit tests for config_loader.py"""

import os
from pathlib import Path

import pytest
import yaml

from config_loader import load_config, _deep_merge


# ── _deep_merge ──────────────────────────────────────────────────

def test_deep_merge_flat():
    base = {"a": 1, "b": 2}
    override = {"b": 99, "c": 3}
    assert _deep_merge(base, override) == {"a": 1, "b": 99, "c": 3}

def test_deep_merge_nested():
    base = {"scoring": {"title": 30, "location": 25}}
    override = {"scoring": {"location": 20}}
    result = _deep_merge(base, override)
    assert result == {"scoring": {"title": 30, "location": 20}}

def test_deep_merge_override_wins_on_conflict():
    base = {"key": "base_value"}
    override = {"key": "new_value"}
    assert _deep_merge(base, override)["key"] == "new_value"

def test_deep_merge_does_not_mutate_base():
    base = {"a": {"b": 1}}
    _deep_merge(base, {"a": {"c": 2}})
    assert "c" not in base["a"]

def test_deep_merge_empty_override():
    base = {"a": 1}
    assert _deep_merge(base, {}) == {"a": 1}

def test_deep_merge_empty_base():
    override = {"a": 1}
    assert _deep_merge({}, override) == {"a": 1}


# ── load_config ──────────────────────────────────────────────────

def _write_yaml(path: Path, data: dict):
    with open(path, "w") as f:
        yaml.dump(data, f)


def test_load_config_reads_base(tmp_path):
    _write_yaml(tmp_path / "config.yaml", {"foo": "bar"})
    config = load_config(tmp_path)
    assert config["foo"] == "bar"


def test_load_config_missing_base_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path)


def test_load_config_merges_local(tmp_path):
    _write_yaml(tmp_path / "config.yaml", {"a": 1, "b": 2})
    _write_yaml(tmp_path / "config.local.yaml", {"b": 99})
    config = load_config(tmp_path)
    assert config["a"] == 1
    assert config["b"] == 99


def test_load_config_local_is_optional(tmp_path):
    _write_yaml(tmp_path / "config.yaml", {"a": 1})
    config = load_config(tmp_path)
    assert config["a"] == 1


def test_load_config_env_var_overrides_smtp_server(tmp_path, monkeypatch):
    _write_yaml(tmp_path / "config.yaml", {"email": {"smtp_server": "old.smtp.com"}})
    monkeypatch.setenv("SMTP_SERVER", "new.smtp.com")
    config = load_config(tmp_path)
    assert config["email"]["smtp_server"] == "new.smtp.com"


def test_load_config_env_var_smtp_port_cast_to_int(tmp_path, monkeypatch):
    _write_yaml(tmp_path / "config.yaml", {"email": {"smtp_port": 587}})
    monkeypatch.setenv("SMTP_PORT", "465")
    config = load_config(tmp_path)
    assert config["email"]["smtp_port"] == 465


def test_load_config_env_var_jsearch_key(tmp_path, monkeypatch):
    _write_yaml(tmp_path / "config.yaml", {"api_keys": {}})
    monkeypatch.setenv("JSEARCH_API_KEY", "my-secret-key")
    config = load_config(tmp_path)
    assert config["api_keys"]["jsearch_rapidapi_key"] == "my-secret-key"


def test_load_config_env_var_not_set_leaves_default(tmp_path, monkeypatch):
    _write_yaml(tmp_path / "config.yaml", {"email": {"smtp_server": "original"}})
    monkeypatch.delenv("SMTP_SERVER", raising=False)
    config = load_config(tmp_path)
    assert config["email"]["smtp_server"] == "original"


def test_load_config_env_var_telegram_bot_token(tmp_path, monkeypatch):
    _write_yaml(tmp_path / "config.yaml", {"telegram": {"bot_token": "YOUR_TOKEN"}})
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "real-token-123")
    config = load_config(tmp_path)
    assert config["telegram"]["bot_token"] == "real-token-123"


def test_load_config_env_var_telegram_chat_id(tmp_path, monkeypatch):
    _write_yaml(tmp_path / "config.yaml", {"telegram": {"chat_id": "YOUR_CHAT_ID"}})
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
    config = load_config(tmp_path)
    assert config["telegram"]["chat_id"] == 987654321
