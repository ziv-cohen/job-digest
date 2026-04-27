"""Health status tracking for external dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class SourceNotConfiguredError(Exception):
    """Raised by a source's fetch_jobs() when required credentials are missing.

    main.py catches this and omits the source from the health report entirely,
    since a missing-config source is neither healthy nor broken — just inactive.
    """


@dataclass
class HealthStatus:
    name: str
    ok: bool
    detail: str = ""   # short error summary, empty when ok
    job_count: int = -1  # raw jobs fetched; -1 means not applicable (e.g. LLM)


def check_llm(config: dict[str, Any]) -> HealthStatus:
    """Return LLM health based on whether the API key is configured."""
    api_key = config.get("anthropic", {}).get("api_key", "")
    if api_key and not api_key.startswith("YOUR_"):
        return HealthStatus(name="LLM", ok=True)
    return HealthStatus(name="LLM", ok=False, detail="API key not configured")
