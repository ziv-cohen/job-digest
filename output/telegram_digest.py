"""Send the job digest as a Telegram message via Bot API."""

from __future__ import annotations

import html
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from models import Job
from pipeline.health_check import HealthStatus, status_emoji

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LENGTH = 4096  # Telegram hard limit per message

_WEIGHTS_LABELS: dict[str, tuple[str, str]] = {
    "profile_match": ("🤖", "Profile match"),
    "title":         ("📌", "Title"),
    "location":      ("📍", "Location"),
    "company_type":  ("🏢", "Company type"),
    "seniority":     ("🏷", "Seniority"),
    "freshness":     ("🕐", "Freshness"),
    "conditions":    ("💼", "Conditions"),
}


def send_digest(jobs: list[Job], config: dict[str, Any],
                health: list[HealthStatus] | None = None) -> bool:
    """Send ranked jobs as one or more Telegram messages."""
    tg_cfg = config.get("telegram", {})
    bot_token = tg_cfg.get("bot_token", "")
    chat_id = tg_cfg.get("chat_id", "")

    if not bot_token or bot_token.startswith("YOUR_"):
        logger.warning("Telegram bot token not configured — skipping.")
        return False
    if not chat_id:
        logger.warning("Telegram chat_id not configured — skipping.")
        return False

    if not jobs:
        logger.info("No jobs to send — skipping Telegram digest.")
        return True

    weights = config.get("scoring", {}).get("weights", {})
    tz_name = config.get("output", {}).get("timezone", "UTC")
    messages = _build_messages(jobs, weights, tz_name, health or [])
    url = TELEGRAM_API_URL.format(token=bot_token)

    for i, text in enumerate(messages, 1):
        try:
            resp = requests.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }, timeout=15)
            resp.raise_for_status()
            logger.info("Telegram: sent message %d/%d", i, len(messages))
        except requests.RequestException as exc:
            logger.error("Telegram: failed to send message %d/%d: %s", i, len(messages), exc)
            return False

    return True


def _build_messages(jobs: list[Job], weights: dict[str, int] | None = None,
                    tz_name: str = "UTC",
                    health: list[HealthStatus] | None = None) -> list[str]:
    """Build a list of messages, splitting if content exceeds Telegram's limit."""
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone '%s' — falling back to UTC", tz_name)
        tz = ZoneInfo("UTC")
    now = datetime.now(tz).strftime("%d %b %Y, %H:%M")
    header = f"<b>Job Digest — {now}</b>\n{len(jobs)} matches\n"
    if weights:
        weight_lines = [
            f"{emoji} {label} {weights[cat]}%"
            for cat, (emoji, label) in _WEIGHTS_LABELS.items()
            if weights.get(cat)
        ]
        header += "<i>" + "\n".join(weight_lines) + "</i>\n"

    job_blocks = [_format_job(i, job) for i, job in enumerate(jobs, 1)]

    messages: list[str] = []
    current = header
    for block in job_blocks:
        if len(current) + len(block) > MAX_MESSAGE_LENGTH:
            messages.append(current)
            current = block
        else:
            current += block
    if current:
        messages.append(current)

    if health:
        parts = [
            f"{status_emoji(h)} {html.escape(h.name)}"
            + (f" ({h.job_count})" if h.ok and h.job_count >= 0 else "")
            + (f" ({html.escape(h.detail)})" if not h.ok and h.detail else "")
            for h in health
        ]
        rows = [" · ".join(parts[i:i + 2]) for i in range(0, len(parts), 2)]
        footer = "\n\n<i>🏥 " + "\n    ".join(rows) + "</i>"
        messages[-1] += footer

    return messages


def _format_job(rank: int, job: Job) -> str:
    salary = job.salary_text or job._salary_range() or "Not disclosed"

    location_parts = []
    if job.location:
        location_parts.append(job.location)
    if job.is_remote:
        region = f" ({job.remote_region})" if job.remote_region else ""
        location_parts.append(f"Remote{region}")
    location = " · ".join(location_parts) or "Not specified"

    meta_parts = []
    if job.seniority:
        meta_parts.append(job.seniority.replace("_", " ").title())
    if job.company_type and job.company_type != "unknown":
        meta_parts.append(job.company_type.title())
    if job.has_growth_signals:
        meta_parts.append("Growing company")
    meta = " · ".join(meta_parts)

    date = "Recent"
    if job.date_posted:
        from datetime import timezone
        age_hours = (datetime.now(timezone.utc) - job.date_posted).total_seconds() / 3600
        if age_hours < 24:
            date = "Today"
        elif age_hours < 48:
            date = "Yesterday"
        else:
            date = job.date_posted.strftime("%d %b")

    breakdown_parts = []
    if job.score_breakdown:
        for cat, (emoji, label) in _WEIGHTS_LABELS.items():
            score = job.score_breakdown.get(cat)
            if score is None or score == 0.0:
                continue
            breakdown_parts.append(f"{emoji} {label} {round(score)}")

    e = html.escape
    lines = [
        f"\n<b>#{rank} [{job.score:.0f}%] <a href=\"{job.url}\">{e(job.title)}</a></b>",
        f"🏢 {e(job.company)}",
        f"📍 {e(location)}",
        f"💰 {e(salary)}",
    ]
    if meta:
        lines.append(f"🏷 {e(meta)}")
    if breakdown_parts:
        lines.append(f"📊 {' · '.join(breakdown_parts)}")
    if job.profile_match_rationale:
        lines.append(f"🤖 {e(job.profile_match_rationale)}")
    lines.append(f"🕐 {date} · {job.source.title()}")

    return "\n".join(lines) + "\n"
