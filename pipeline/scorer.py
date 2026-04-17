"""Relevance scoring engine — scores each job against Ziv's criteria."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from models import Job

logger = logging.getLogger(__name__)


def score_jobs(jobs: list[Job], config: dict[str, Any]) -> list[Job]:
    """Apply rule-based scorers to all jobs. profile_match is left at 0.0 —
    call match_profile() then recompute_scores() on the filtered subset afterwards.
    """
    scoring_cfg = config["scoring"]
    weights = scoring_cfg["weights"]

    for job in jobs:
        # Pre-compute enrichment flag used by title scorer and digest output
        job.has_growth_signals = _has_growth_signals(f"{job.title} {job.description}".lower())

        breakdown: dict[str, float] = {}
        breakdown["profile_match"] = 0.0  # filled later by match_profile
        breakdown["title"] = _score_title(job, scoring_cfg)
        breakdown["location"] = _score_location(job, scoring_cfg)
        breakdown["company_type"] = _score_company_type(job, scoring_cfg)
        breakdown["seniority"] = _score_seniority(job, scoring_cfg)
        breakdown["freshness"] = _score_freshness(job, scoring_cfg)
        breakdown["conditions"] = _score_conditions(job, scoring_cfg)
        job.score_breakdown = breakdown
        job.score = sum(breakdown[cat] * weights[cat] / 100 for cat in weights)

    return jobs


def recompute_scores(jobs: list[Job], config: dict[str, Any]) -> None:
    """Recompute job.score from the current breakdown values.

    Call after match_profile() has filled breakdown["profile_match"].
    """
    weights = config["scoring"]["weights"]
    for job in jobs:
        job.score = sum(job.score_breakdown[cat] * weights[cat] / 100 for cat in weights)
    logger.info("Scoring complete: min=%.1f, max=%.1f, mean=%.1f",
                min(j.score for j in jobs) if jobs else 0,
                max(j.score for j in jobs) if jobs else 0,
                sum(j.score for j in jobs) / len(jobs) if jobs else 0)


# ── Title match ─────────────────────────────────────────────────

_TITLE_PATTERNS = {
    "director": [
        r"engineering\s+director",
        r"director\s+of\s+engineering",
        r"director.*engineering",
        r"group\s+director.*engineer",
        r"software\s+engineering\s+director",
    ],
    "senior_em": [
        r"senior\s+engineering\s+manager",
        r"sr\.?\s+engineering\s+manager",
    ],
    "em": [
        r"engineering\s+manager",
    ],
    "vp": [
        r"vp\s+(?:of\s+)?engineering",
        r"vice\s+president.*engineering",
    ],
    "head": [
        r"head\s+of\s+engineering",
    ],
    "founding_cto": [
        r"founding\s+cto",
        r"co-?founder.*cto",
        r"cto.*co-?found",
        r"cto.*early\s+stage",
    ],
    "cto": [
        r"\bcto\b",
        r"chief\s+technology\s+officer",
    ],
}


_EXCLUDED_DOMAINS = ["hardware", "mechanical", "electrical", "civil", "firmware"]


def _score_title(job: Job, cfg: dict) -> float:
    title_cfg = cfg["title_match"]
    title_lower = job.title.lower()

    # Hard-exclude non-software engineering domains
    if any(kw in title_lower for kw in _EXCLUDED_DOMAINS):
        return 0.0

    for pattern in _TITLE_PATTERNS["director"]:
        if re.search(pattern, title_lower):
            job.seniority = job.seniority or "director"
            return title_cfg["exact_director"]

    for pattern in _TITLE_PATTERNS["vp"]:
        if re.search(pattern, title_lower):
            job.seniority = job.seniority or "vp"
            return title_cfg["exact_vp"]

    for pattern in _TITLE_PATTERNS["head"]:
        if re.search(pattern, title_lower):
            job.seniority = job.seniority or "director"
            return title_cfg["exact_director"]

    for pattern in _TITLE_PATTERNS["founding_cto"]:
        if re.search(pattern, title_lower):
            job.seniority = job.seniority or "cto"
            return title_cfg["founding_cto"]

    for pattern in _TITLE_PATTERNS["cto"]:
        if re.search(pattern, title_lower):
            job.seniority = job.seniority or "cto"
            return title_cfg["exact_cto"]

    for pattern in _TITLE_PATTERNS["senior_em"]:
        if re.search(pattern, title_lower):
            job.seniority = job.seniority or "senior_manager"
            return title_cfg["exact_senior_em"]

    for pattern in _TITLE_PATTERNS["em"]:
        if re.search(pattern, title_lower):
            job.seniority = job.seniority or "manager"
            score = title_cfg["exact_em"]
            if job.has_growth_signals:
                score = min(score + title_cfg["em_growth_boost"], 100.0)
            return score

    # Partial match — title contains relevant keywords but not exact
    partial_kw = ["engineering", "platform", "infrastructure", "backend"]
    leader_kw = ["manager", "director", "lead", "head", "vp", "chief"]
    has_tech = any(kw in title_lower for kw in partial_kw)
    has_leader = any(kw in title_lower for kw in leader_kw)
    if has_tech and has_leader:
        return title_cfg["partial_match"]

    return 0.0


# ── Location fit ────────────────────────────────────────────────

def _score_location(job: Job, cfg: dict) -> float:
    loc_cfg = cfg["location_fit"]
    loc_lower = (job.location or "").lower()

    # Prague on-site or hybrid
    prague_indicators = ["prague", "praha"]
    is_prague = any(p in loc_lower for p in prague_indicators)

    if is_prague:
        return loc_cfg["prague_onsite_hybrid"]  # Prague + remote = best of both

    # EMEA remote
    if job.is_remote and job.remote_region == "EMEA":
        return loc_cfg["emea_remote"]

    # Worldwide remote (may or may not pay EMEA rates)
    if job.is_remote and job.remote_region == "Worldwide":
        return loc_cfg["worldwide_remote"]

    # Czech Republic (not Prague)
    czech_indicators = ["czech", "\u010desk", "brno", "plzen", "plze\u0148", "kutna hora", "kutn\u00e1 hora"]
    if any(c in loc_lower for c in czech_indicators):
        if job.is_remote:
            return loc_cfg["czech_remote"]
        return loc_cfg["commute_2hr"]  # Czech cities are close enough for on-site

    # Cities within ~2hr by train — hybrid/remote only
    cities_2hr = ["dresden"]
    if any(city in loc_lower for city in cities_2hr):
        if not job.is_remote:
            return loc_cfg["distant_onsite"]
        return loc_cfg["commute_2hr"]

    # Cities within ~4hr by train — hybrid/remote only
    cities_4hr = ["ostrava", "wroclaw", "bratislava", "vienna", "wien", "berlin"]
    if any(city in loc_lower for city in cities_4hr):
        if not job.is_remote:
            return loc_cfg["distant_onsite"]
        return loc_cfg["commute_4hr"]

    # API-tagged remote but no region info
    if job.is_remote:
        return loc_cfg["generic_remote"]

    # Known location but not relevant (distant on-site city)
    if loc_lower:
        return loc_cfg["distant_onsite"]

    # No location data at all — pass gracefully, let LLM and other signals decide
    return loc_cfg["no_location_info"]


# ── Company type ────────────────────────────────────────────────

_PRODUCT_SIGNALS = [
    "saas", "platform", "product", "b2b", "b2c", "marketplace",
    "fintech", "healthtech", "edtech", "proptech", "regtech",
    "series a", "series b", "series c", "series d", "seed",
    "venture", "startup", "scale-up", "scaleup",
]
_CONSULTING_SIGNALS = ["consulting", "consultancy", "advisory", "professional services"]
_OUTSOURCING_SIGNALS = ["outsourc", "staff augment", "body shop", "nearshore", "offshore"]


def _score_company_type(job: Job, cfg: dict) -> float:
    type_cfg = cfg["company_type"]
    text = f"{job.company} {job.description}".lower()

    # Already tagged by source
    if job.company_type == "product":
        return type_cfg["product_company"]

    if any(s in text for s in _PRODUCT_SIGNALS):
        job.company_type = job.company_type or "product"
        return type_cfg["product_company"]

    if any(s in text for s in _OUTSOURCING_SIGNALS):
        job.company_type = job.company_type or "outsourcing"
        return type_cfg["outsourcing"]

    if any(s in text for s in _CONSULTING_SIGNALS):
        job.company_type = job.company_type or "consulting"
        return type_cfg["consulting"]

    job.company_type = job.company_type or "unknown"
    return type_cfg["unknown"]


# ── Seniority ───────────────────────────────────────────────────

def _score_seniority(job: Job, cfg: dict) -> float:
    sen_cfg = cfg["seniority"]
    seniority = job.seniority.lower() if job.seniority else ""

    # May have been set during title scoring
    if seniority == "cto":
        return sen_cfg["cto_level"]
    if seniority == "vp":
        return sen_cfg["vp_level"]
    if seniority == "director":
        return sen_cfg["director_level"]
    if seniority == "senior_manager":
        return sen_cfg["senior_manager"]
    if seniority == "manager":
        return sen_cfg["manager"]

    # Infer from title if not yet set
    title_lower = job.title.lower()
    if any(re.search(p, title_lower) for p in _TITLE_PATTERNS["cto"]):
        job.seniority = "cto"
        return sen_cfg["cto_level"]
    if any(kw in title_lower for kw in ["vp ", "vice president"]):
        job.seniority = "vp"
        return sen_cfg["vp_level"]
    if any(kw in title_lower for kw in ["director", "head of engineering", "chief"]):
        job.seniority = "director"
        return sen_cfg["director_level"]
    if "senior" in title_lower and "manager" in title_lower:
        job.seniority = "senior_manager"
        return sen_cfg["senior_manager"]
    if "manager" in title_lower:
        job.seniority = "manager"
        return sen_cfg["manager"]

    return sen_cfg["unclear"]


# ── Freshness ───────────────────────────────────────────────────

def _score_freshness(job: Job, cfg: dict) -> float:
    fresh_cfg = cfg["freshness"]

    if not job.date_posted:
        return fresh_cfg["four_to_seven_days"]  # conservative default

    now = datetime.now(timezone.utc)
    if job.date_posted.tzinfo is None:
        job.date_posted = job.date_posted.replace(tzinfo=timezone.utc)

    age_hours = (now - job.date_posted).total_seconds() / 3600

    if age_hours <= 24:
        return fresh_cfg["today"]
    if age_hours <= 48:
        return fresh_cfg["yesterday"]
    if age_hours <= 72:
        return fresh_cfg["two_to_three_days"]
    return fresh_cfg["four_to_seven_days"]


# ── Conditions ──────────────────────────────────────────────────

def _score_conditions(job: Job, cfg: dict) -> float:
    cond_cfg = cfg["conditions"]
    text = f"{job.title} {job.description}".lower()
    score = 0.0

    # Freelancer-friendly
    freelance_kw = ["freelance", "contractor", "contract", "b2b", "self-employed", "i\u010do", "\u017eivnost"]
    if any(kw in text for kw in freelance_kw):
        job.job_type = job.job_type or "freelancer"
        score += cond_cfg["freelancer_friendly"]

    # Salary mentioned
    if job.salary_min or job.salary_max or job.salary_text:
        score += cond_cfg["salary_mentioned"]

    # Growth signals (pre-computed in score_jobs)
    if job.has_growth_signals:
        score += cond_cfg["growth_signals"]

    return min(score, 100.0)


def _has_growth_signals(text: str) -> bool:
    growth_kw = [
        "fast-growing", "fast growing", "hypergrowth", "hyper-growth",
        "scaling", "scale-up", "scaleup", "series a", "series b",
        "series c", "series d", "rapidly growing", "high growth",
        "expanding", "doubling",
    ]
    return any(kw in text for kw in growth_kw)
