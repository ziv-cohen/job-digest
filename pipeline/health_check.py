"""Health status tracking for external dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HealthStatus:
    name: str
    ok: bool
    detail: str = ""  # short error summary, empty when ok


def check_llm(config: dict[str, Any]) -> HealthStatus:
    """Return LLM health based on whether the API key is configured."""
    api_key = config.get("anthropic", {}).get("api_key", "")
    if api_key and not api_key.startswith("YOUR_"):
        return HealthStatus(name="LLM", ok=True)
    return HealthStatus(name="LLM", ok=False, detail="API key not configured")
