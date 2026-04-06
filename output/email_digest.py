"""Build and send the daily HTML email digest."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from models import Job

logger = logging.getLogger(__name__)


def send_digest(jobs: list[Job], config: dict[str, Any]) -> bool:
    """Build HTML email from ranked jobs and send via SMTP."""
    email_cfg = config["email"]

    if not jobs:
        logger.info("No jobs to send — skipping digest.")
        return True

    html = _build_html(jobs)
    plain = _build_plain(jobs)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Job Digest — {len(jobs)} matches ({datetime.now().strftime('%d %b %Y')})"
    msg["From"] = email_cfg["sender_email"]
    msg["To"] = email_cfg["recipient_email"]

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        server = smtplib.SMTP(email_cfg["smtp_server"], int(email_cfg["smtp_port"]))
        server.starttls()
        server.login(email_cfg["sender_email"], email_cfg["sender_password"])
        server.sendmail(email_cfg["sender_email"], email_cfg["recipient_email"], msg.as_string())
        server.quit()
        logger.info("Digest sent to %s with %d jobs.", email_cfg["recipient_email"], len(jobs))
        return True
    except Exception as exc:
        logger.error("Failed to send digest: %s", exc)
        return False


def _build_html(jobs: list[Job]) -> str:
    """Generate the HTML email body."""
    today = datetime.now().strftime("%A, %d %B %Y")

    rows = ""
    for i, job in enumerate(jobs, 1):
        # Score badge color
        if job.score >= 70:
            badge_bg = "#0F6E56"
            badge_fg = "#E1F5EE"
        elif job.score >= 50:
            badge_bg = "#185FA5"
            badge_fg = "#E6F1FB"
        else:
            badge_bg = "#5F5E5A"
            badge_fg = "#F1EFE8"

        # Location display
        loc_parts = []
        if job.location:
            loc_parts.append(job.location)
        if job.is_remote:
            region = f" ({job.remote_region})" if job.remote_region else ""
            loc_parts.append(f"Remote{region}")
        location_display = " · ".join(loc_parts) or "Not specified"

        # Salary display
        salary_display = job.salary_text or job._salary_range() or "Not disclosed"

        # Type/seniority display
        meta_parts = []
        if job.seniority:
            meta_parts.append(job.seniority.replace("_", " ").title())
        if job.company_type and job.company_type != "unknown":
            meta_parts.append(job.company_type.replace("_", " ").title())
        if job.employment_type:
            meta_parts.append(job.employment_type.replace("_", " ").title())
        if job.job_type:
            meta_parts.append(f"Hiring: {job.job_type}")
        if job.has_growth_signals:
            meta_parts.append("Growing company")
        meta_display = " · ".join(meta_parts) or ""

        # Date display
        if job.date_posted:
            age_hours = (datetime.utcnow() - job.date_posted.replace(tzinfo=None)).total_seconds() / 3600
            if age_hours < 24:
                date_display = "Today"
            elif age_hours < 48:
                date_display = "Yesterday"
            else:
                date_display = job.date_posted.strftime("%d %b")
        else:
            date_display = "Recent"

        # Score breakdown tooltip text
        breakdown_parts = [f"{k}: {v:.0f}" for k, v in job.score_breakdown.items() if v > 0]
        breakdown_text = " | ".join(breakdown_parts)

        rows += f"""
        <tr style="border-bottom: 1px solid #e8e6df;">
          <td style="padding: 16px 12px; vertical-align: top; width: 50px; text-align: center;">
            <div style="background: {badge_bg}; color: {badge_fg}; font-weight: 600;
                        font-size: 14px; border-radius: 6px; padding: 4px 8px;
                        display: inline-block; min-width: 32px;" title="{breakdown_text}">
              {job.score:.0f}
            </div>
          </td>
          <td style="padding: 16px 12px;">
            <a href="{job.url}" style="color: #185FA5; font-weight: 600; font-size: 15px;
                     text-decoration: none; line-height: 1.3;">{job.title}</a>
            <div style="color: #444441; font-size: 14px; margin-top: 3px; font-weight: 500;">
              {job.company}
            </div>
            <div style="color: #888780; font-size: 13px; margin-top: 4px; line-height: 1.5;">
              📍 {location_display}<br/>
              💰 {salary_display}<br/>
              {f'🏷️ {meta_display}<br/>' if meta_display else ''}
              🕐 {date_display} · via {job.source.title()}
            </div>
            <div style="color: #B4B2A9; font-size: 11px; margin-top: 4px;">
              Score: {breakdown_text}
            </div>
          </td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="margin: 0; padding: 0; background: #F5F4F0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
  <div style="max-width: 640px; margin: 0 auto; padding: 24px 16px;">

    <!-- Header -->
    <div style="background: #26215C; color: #EEEDFE; padding: 24px 20px; border-radius: 12px 12px 0 0;">
      <h1 style="margin: 0; font-size: 22px; font-weight: 600;">Job Digest</h1>
      <p style="margin: 6px 0 0; font-size: 14px; opacity: 0.8;">{today} · {len(jobs)} matches</p>
    </div>

    <!-- Jobs table -->
    <table style="width: 100%; background: #FFFFFF; border-collapse: collapse;
                  border-radius: 0 0 12px 12px; overflow: hidden;">
      {rows}
    </table>

    <!-- Footer -->
    <div style="text-align: center; padding: 20px; color: #B4B2A9; font-size: 12px;">
      Generated by Job Digest Pipeline · Scores: title (30) + location (25) +
      company type (20) + seniority (15) + freshness (10) + bonus
    </div>

  </div>
</body>
</html>"""


def _build_plain(jobs: list[Job]) -> str:
    """Generate plain-text fallback."""
    lines = [f"Job Digest — {len(jobs)} matches ({datetime.now().strftime('%d %b %Y')})", "=" * 60, ""]

    for i, job in enumerate(jobs, 1):
        loc = job.location or "N/A"
        remote_tag = " [REMOTE]" if job.is_remote else ""
        salary = job.salary_text or job._salary_range() or "Not disclosed"

        lines.append(f"#{i}  Score: {job.score:.0f}")
        lines.append(f"    {job.title}")
        lines.append(f"    {job.company}")
        lines.append(f"    Location: {loc}{remote_tag}")
        lines.append(f"    Salary: {salary}")
        if job.seniority:
            lines.append(f"    Seniority: {job.seniority}")
        if job.company_type and job.company_type != "unknown":
            lines.append(f"    Company type: {job.company_type}")
        lines.append(f"    Posted: {job.date_posted.strftime('%d %b') if job.date_posted else 'Recent'}")
        lines.append(f"    Source: {job.source}")
        lines.append(f"    Apply: {job.url}")
        breakdown = " | ".join(f"{k}:{v:.0f}" for k, v in job.score_breakdown.items() if v > 0)
        lines.append(f"    Breakdown: {breakdown}")
        lines.append("")

    return "\n".join(lines)
