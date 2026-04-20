"""Canonical Job model used throughout the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Job:
    """A single job listing normalised to a common schema."""

    # --- Identity ---
    title: str
    company: str
    url: str
    source: str                          # e.g. "jsearch", "adzuna", "remotive"

    # --- Location ---
    location: str = ""                   # human-readable, e.g. "Prague, CZ"
    is_remote: bool = False
    remote_region: str = ""              # e.g. "EMEA", "Worldwide", ""

    # --- Dates ---
    date_posted: Optional[datetime] = None
    date_fetched: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # --- Compensation ---
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = ""
    salary_text: str = ""                # raw text if parsing fails
    salary_is_estimated: bool = False    # site-estimated, not provided by employer

    # --- Metadata ---
    description: str = ""
    employment_type: str = ""            # "full_time", "contract", "freelance"
    seniority: str = ""                  # "director", "senior_manager", "manager"
    company_type: str = ""               # "product", "outsourcing", "consulting"
    job_type: str = ""                   # "employee", "freelancer", "both"

    # --- Pipeline fields (filled during processing) ---
    score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    dedup_key: str = ""                  # generated during dedup
    has_growth_signals: bool = False     # set during scoring, shown in digest
    profile_match_rationale: str = ""   # one-line LLM rationale, shown in digest

    def to_dict(self) -> dict:
        """Serialise for JSON / email template."""
        return {
            "title": self.title,
            "company": self.company,
            "url": self.url,
            "source": self.source,
            "location": self.location,
            "is_remote": self.is_remote,
            "remote_region": self.remote_region,
            "date_posted": self.date_posted.isoformat() if self.date_posted else "",
            "salary_text": self.salary_text or self._salary_range(),
            "employment_type": self.employment_type,
            "seniority": self.seniority,
            "company_type": self.company_type,
            "job_type": self.job_type,
            "score": round(self.score, 1),
            "score_breakdown": self.score_breakdown,
            "has_growth_signals": self.has_growth_signals,
            "profile_match_rationale": self.profile_match_rationale,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        """Reconstruct a Job from a to_dict() payload (e.g. dry_run_results.json)."""
        date_posted = None
        if d.get("date_posted"):
            date_posted = datetime.fromisoformat(d["date_posted"])
        return cls(
            title=d["title"],
            company=d["company"],
            url=d["url"],
            source=d["source"],
            location=d.get("location", ""),
            is_remote=d.get("is_remote", False),
            remote_region=d.get("remote_region", ""),
            date_posted=date_posted,
            salary_text=d.get("salary_text", ""),
            employment_type=d.get("employment_type", ""),
            seniority=d.get("seniority", ""),
            company_type=d.get("company_type", ""),
            job_type=d.get("job_type", ""),
            score=d.get("score", 0.0),
            score_breakdown=d.get("score_breakdown", {}),
            has_growth_signals=d.get("has_growth_signals", False),
            profile_match_rationale=d.get("profile_match_rationale", ""),
        )

    def _salary_range(self) -> str:
        cur = self.salary_currency or ""
        if self.salary_min and self.salary_max:
            if self.salary_min == self.salary_max:
                text = f"{cur} {self.salary_min:,.0f}".strip()
            else:
                text = f"{cur} {self.salary_min:,.0f} – {self.salary_max:,.0f}".strip()
        elif self.salary_min:
            text = f"{cur} {self.salary_min:,.0f}+".strip()
        else:
            return ""
        return f"{text} (estimated)" if self.salary_is_estimated else text

    def __repr__(self) -> str:
        return f"Job({self.title!r} @ {self.company!r}, score={self.score:.1f})"
