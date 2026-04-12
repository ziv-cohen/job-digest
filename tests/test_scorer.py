"""Unit tests for pipeline/scorer.py"""

from datetime import datetime, timedelta, timezone

from models import Job
from pipeline.scorer import (
    score_jobs,
    _score_title,
    _score_location,
    _score_company_type,
    _score_seniority,
    _score_freshness,
    _score_conditions,
    _has_growth_signals,
)


def make_job(**kwargs) -> Job:
    defaults = dict(
        title="Engineering Manager",
        company="Acme",
        url="https://example.com/job/1",
        source="jsearch",
    )
    return Job(**{**defaults, **kwargs})


# ── _has_growth_signals ──────────────────────────────────────────

def test_growth_signals_series_a():
    assert _has_growth_signals("we just closed series a funding") is True

def test_growth_signals_fast_growing():
    assert _has_growth_signals("fast-growing startup") is True

def test_growth_signals_hypergrowth():
    assert _has_growth_signals("hypergrowth environment") is True

def test_growth_signals_scaling():
    assert _has_growth_signals("scaling our engineering team") is True

def test_growth_signals_no_match():
    assert _has_growth_signals("stable enterprise company") is False

def test_growth_signals_empty():
    assert _has_growth_signals("") is False


# ── _score_title ─────────────────────────────────────────────────
# Config values are direct 0-100 scores.

def test_title_engineering_director(scoring_cfg):
    job = make_job(title="Engineering Director")
    assert _score_title(job, scoring_cfg) == 100
    assert job.seniority == "director"

def test_title_director_of_engineering(scoring_cfg):
    job = make_job(title="Director of Engineering")
    assert _score_title(job, scoring_cfg) == 100

def test_title_head_of_engineering(scoring_cfg):
    job = make_job(title="Head of Engineering")
    assert _score_title(job, scoring_cfg) == 100

def test_title_vp_engineering(scoring_cfg):
    job = make_job(title="VP Engineering")
    assert _score_title(job, scoring_cfg) == 100
    assert job.seniority == "vp"

def test_title_vp_of_engineering(scoring_cfg):
    job = make_job(title="VP of Engineering")
    assert _score_title(job, scoring_cfg) == 100
    assert job.seniority == "vp"

def test_title_head_of_engineering_tagged_director(scoring_cfg):
    job = make_job(title="Head of Engineering")
    _score_title(job, scoring_cfg)
    assert job.seniority == "director"

def test_title_founding_cto(scoring_cfg):
    job = make_job(title="Founding CTO")
    assert _score_title(job, scoring_cfg) == 100

def test_title_standalone_cto(scoring_cfg):
    job = make_job(title="CTO")
    assert _score_title(job, scoring_cfg) == 90
    assert job.seniority == "cto"

def test_title_chief_technology_officer(scoring_cfg):
    job = make_job(title="Chief Technology Officer")
    assert _score_title(job, scoring_cfg) == 90
    assert job.seniority == "cto"

def test_title_founding_cto_tagged_as_cto(scoring_cfg):
    job = make_job(title="Founding CTO")
    _score_title(job, scoring_cfg)
    assert job.seniority == "cto"

def test_title_senior_engineering_manager(scoring_cfg):
    job = make_job(title="Senior Engineering Manager")
    assert _score_title(job, scoring_cfg) == 85
    assert job.seniority == "senior_manager"

def test_title_sr_engineering_manager(scoring_cfg):
    job = make_job(title="Sr. Engineering Manager")
    assert _score_title(job, scoring_cfg) == 85

def test_title_engineering_manager_no_growth(scoring_cfg):
    job = make_job(title="Engineering Manager")
    job.has_growth_signals = False
    assert _score_title(job, scoring_cfg) == 60
    assert job.seniority == "manager"

def test_title_engineering_manager_with_growth(scoring_cfg):
    job = make_job(title="Engineering Manager")
    job.has_growth_signals = True
    assert _score_title(job, scoring_cfg) == 75  # 60 + 15

def test_title_partial_match_tech_and_lead(scoring_cfg):
    job = make_job(title="Platform Engineering Lead")
    assert _score_title(job, scoring_cfg) == 35

def test_title_data_director_no_match(scoring_cfg):
    # "data" alone is no longer a tech keyword — prevents "HR Data Director" matching
    job = make_job(title="HR Data Director")
    assert _score_title(job, scoring_cfg) == 0

def test_title_data_director_no_partial_match(scoring_cfg):
    # "data" removed from partial_kw — not a target domain
    job = make_job(title="Data Director")
    assert _score_title(job, scoring_cfg) == 0

def test_title_hardware_excluded(scoring_cfg):
    job = make_job(title="Global Hardware Engineering Director")
    assert _score_title(job, scoring_cfg) == 0

def test_title_electrical_excluded(scoring_cfg):
    job = make_job(title="Associate Director - Electrical Engineering")
    assert _score_title(job, scoring_cfg) == 0

def test_title_no_match(scoring_cfg):
    job = make_job(title="Product Manager")
    assert _score_title(job, scoring_cfg) == 0

def test_title_does_not_overwrite_existing_seniority(scoring_cfg):
    job = make_job(title="Engineering Director", seniority="senior_manager")
    _score_title(job, scoring_cfg)
    assert job.seniority == "senior_manager"  # pre-existing value preserved


# ── _score_location ──────────────────────────────────────────────
# Config values are direct 0-100 scores.

def test_location_prague_onsite(scoring_cfg):
    job = make_job(location="Prague, CZ", is_remote=False)
    assert _score_location(job, scoring_cfg) == 100

def test_location_prague_remote(scoring_cfg):
    job = make_job(location="Prague", is_remote=True)
    assert _score_location(job, scoring_cfg) == 100

def test_location_emea_remote(scoring_cfg):
    job = make_job(location="Europe", is_remote=True, remote_region="EMEA")
    assert _score_location(job, scoring_cfg) == 100

def test_location_worldwide_remote(scoring_cfg):
    job = make_job(location="Worldwide", is_remote=True, remote_region="Worldwide")
    assert _score_location(job, scoring_cfg) == 90

def test_location_czech_remote(scoring_cfg):
    job = make_job(location="Brno, Czech Republic", is_remote=True)
    assert _score_location(job, scoring_cfg) == 80

def test_location_czech_onsite(scoring_cfg):
    job = make_job(location="Brno, Czech Republic", is_remote=False)
    assert _score_location(job, scoring_cfg) == 50

def test_location_ostrava_hybrid(scoring_cfg):
    job = make_job(location="Ostrava, CZ", is_remote=True)
    assert _score_location(job, scoring_cfg) == 25

def test_location_ostrava_onsite_scores_zero(scoring_cfg):
    job = make_job(location="Ostrava, CZ", is_remote=False)
    assert _score_location(job, scoring_cfg) == 0

def test_location_kutna_hora_onsite(scoring_cfg):
    job = make_job(location="Kutna Hora, CZ", is_remote=False)
    assert _score_location(job, scoring_cfg) == 50

def test_location_plzen_onsite(scoring_cfg):
    job = make_job(location="Plzen, CZ", is_remote=False)
    assert _score_location(job, scoring_cfg) == 50

def test_location_2hr_city_hybrid(scoring_cfg):
    job = make_job(location="Dresden, Germany", is_remote=True)
    assert _score_location(job, scoring_cfg) == 50

def test_location_2hr_city_onsite_scores_zero(scoring_cfg):
    job = make_job(location="Dresden, Germany", is_remote=False)
    assert _score_location(job, scoring_cfg) == 0

def test_location_4hr_city_vienna_hybrid(scoring_cfg):
    job = make_job(location="Vienna, Austria", is_remote=True)
    assert _score_location(job, scoring_cfg) == 25

def test_location_4hr_city_vienna_onsite_scores_zero(scoring_cfg):
    job = make_job(location="Vienna, Austria", is_remote=False)
    assert _score_location(job, scoring_cfg) == 0

def test_location_4hr_city_berlin_hybrid(scoring_cfg):
    job = make_job(location="Berlin, Germany", is_remote=True)
    assert _score_location(job, scoring_cfg) == 25

def test_location_4hr_city_bratislava_hybrid(scoring_cfg):
    job = make_job(location="Bratislava, Slovakia", is_remote=True)
    assert _score_location(job, scoring_cfg) == 25

def test_location_beyond_4hr_scores_zero(scoring_cfg):
    job = make_job(location="Munich, Germany", is_remote=False)
    assert _score_location(job, scoring_cfg) == 0

def test_location_generic_remote(scoring_cfg):
    job = make_job(location="", is_remote=True, remote_region="")
    assert _score_location(job, scoring_cfg) == 40

def test_location_unclear(scoring_cfg):
    job = make_job(location="New York, US", is_remote=False)
    assert _score_location(job, scoring_cfg) == 0


# ── _score_company_type ──────────────────────────────────────────
# Config values are direct 0-100 scores.

def test_company_type_pretagged_product(scoring_cfg):
    job = make_job(company_type="product")
    assert _score_company_type(job, scoring_cfg) == 100

def test_company_type_saas_in_description(scoring_cfg):
    job = make_job(description="We are a SaaS company")
    assert _score_company_type(job, scoring_cfg) == 100
    assert job.company_type == "product"

def test_company_type_startup(scoring_cfg):
    job = make_job(description="Series B startup scaling fast")
    assert _score_company_type(job, scoring_cfg) == 100

def test_company_type_outsourcing(scoring_cfg):
    job = make_job(description="Staff augmentation and nearshore delivery")
    assert _score_company_type(job, scoring_cfg) == 75
    assert job.company_type == "outsourcing"

def test_company_type_consulting(scoring_cfg):
    job = make_job(description="Top-tier management consulting firm")
    assert _score_company_type(job, scoring_cfg) == 40
    assert job.company_type == "consulting"

def test_company_type_unknown(scoring_cfg):
    job = make_job(description="We build things")
    assert _score_company_type(job, scoring_cfg) == 0
    assert job.company_type == "unknown"


# ── _score_seniority ─────────────────────────────────────────────
# Config values are direct 0-100 scores.

def test_seniority_cto_pretagged(scoring_cfg):
    job = make_job(seniority="cto")
    assert _score_seniority(job, scoring_cfg) == 100

def test_seniority_vp_pretagged(scoring_cfg):
    job = make_job(seniority="vp")
    assert _score_seniority(job, scoring_cfg) == 100

def test_seniority_director_pretagged(scoring_cfg):
    job = make_job(seniority="director")
    assert _score_seniority(job, scoring_cfg) == 100

def test_seniority_inferred_from_cto_title(scoring_cfg):
    job = make_job(title="CTO", seniority="")
    assert _score_seniority(job, scoring_cfg) == 100
    assert job.seniority == "cto"

def test_seniority_senior_manager_pretagged(scoring_cfg):
    job = make_job(seniority="senior_manager")
    assert _score_seniority(job, scoring_cfg) == 80

def test_seniority_manager_pretagged(scoring_cfg):
    job = make_job(seniority="manager")
    assert _score_seniority(job, scoring_cfg) == 55

def test_seniority_inferred_from_vp_title(scoring_cfg):
    job = make_job(title="VP of Product", seniority="")
    assert _score_seniority(job, scoring_cfg) == 100
    assert job.seniority == "vp"

def test_seniority_inferred_senior_manager_from_title(scoring_cfg):
    job = make_job(title="Senior Product Manager", seniority="")
    assert _score_seniority(job, scoring_cfg) == 80

def test_seniority_inferred_manager_from_title(scoring_cfg):
    job = make_job(title="Project Manager", seniority="")
    assert _score_seniority(job, scoring_cfg) == 55

def test_seniority_unclear(scoring_cfg):
    job = make_job(title="Software Engineer", seniority="")
    assert _score_seniority(job, scoring_cfg) == 0


# ── _score_freshness ─────────────────────────────────────────────
# Config values are direct 0-100 scores.

def test_freshness_today(scoring_cfg):
    job = make_job(date_posted=datetime.now(timezone.utc) - timedelta(hours=2))
    assert _score_freshness(job, scoring_cfg) == 100

def test_freshness_yesterday(scoring_cfg):
    job = make_job(date_posted=datetime.now(timezone.utc) - timedelta(hours=30))
    assert _score_freshness(job, scoring_cfg) == 70

def test_freshness_two_days(scoring_cfg):
    job = make_job(date_posted=datetime.now(timezone.utc) - timedelta(hours=60))
    assert _score_freshness(job, scoring_cfg) == 40

def test_freshness_older(scoring_cfg):
    job = make_job(date_posted=datetime.now(timezone.utc) - timedelta(days=5))
    assert _score_freshness(job, scoring_cfg) == 20

def test_freshness_no_date_defaults_conservative(scoring_cfg):
    job = make_job(date_posted=None)
    assert _score_freshness(job, scoring_cfg) == 20

def test_freshness_naive_datetime_treated_as_utc(scoring_cfg):
    naive = datetime.now() - timedelta(hours=1)
    job = make_job(date_posted=naive)
    assert _score_freshness(job, scoring_cfg) == 100


# ── _score_conditions ────────────────────────────────────────────
# Values are summed and capped at 100.

def test_conditions_salary_disclosed(scoring_cfg):
    job = make_job(salary_min=100000)
    job.has_growth_signals = False
    assert _score_conditions(job, scoring_cfg) == 25

def test_conditions_salary_text(scoring_cfg):
    job = make_job(salary_text="€120k–150k")
    job.has_growth_signals = False
    assert _score_conditions(job, scoring_cfg) == 25

def test_conditions_freelancer_keyword(scoring_cfg):
    job = make_job(description="Open to B2B contract")
    job.has_growth_signals = False
    assert _score_conditions(job, scoring_cfg) == 40
    assert job.job_type == "freelancer"

def test_conditions_growth_signals(scoring_cfg):
    job = make_job()
    job.has_growth_signals = True
    assert _score_conditions(job, scoring_cfg) == 35

def test_conditions_all_signals(scoring_cfg):
    job = make_job(description="Series B startup, contract OK", salary_min=120000)
    job.has_growth_signals = True
    assert _score_conditions(job, scoring_cfg) == 100  # 38+25+37=100, capped

def test_conditions_none(scoring_cfg):
    job = make_job()
    job.has_growth_signals = False
    assert _score_conditions(job, scoring_cfg) == 0


# ── score_jobs (integration) ─────────────────────────────────────

def test_score_jobs_sets_score_and_breakdown(full_config):
    jobs = [make_job(
        title="Engineering Director",
        location="Prague, CZ",
        is_remote=False,
        company_type="product",
        seniority="director",
        date_posted=datetime.now(timezone.utc) - timedelta(hours=1),
    )]
    result = score_jobs(jobs, full_config)
    job = result[0]
    assert job.score > 0
    assert "title" in job.score_breakdown
    assert "location" in job.score_breakdown
    assert "freshness" in job.score_breakdown
    assert "conditions" in job.score_breakdown
    assert "profile_match" in job.score_breakdown

def test_score_jobs_profile_match_uses_fallback_when_unconfigured(full_config):
    # full_config has no anthropic section — match_profile degrades to fallback_score (50)
    jobs = [make_job(title="Engineering Director")]
    score_jobs(jobs, full_config)
    assert jobs[0].score_breakdown["profile_match"] == 50.0

def test_score_jobs_score_is_0_to_100(full_config):
    jobs = [make_job(
        title="Engineering Director",
        location="Prague, CZ",
        is_remote=False,
        company_type="product",
        seniority="director",
        date_posted=datetime.now(timezone.utc) - timedelta(hours=1),
    )]
    score_jobs(jobs, full_config)
    assert 0.0 <= jobs[0].score <= 100.0

def test_score_jobs_sets_growth_signals_flag(full_config):
    jobs = [make_job(description="We are a fast-growing series B startup")]
    score_jobs(jobs, full_config)
    assert jobs[0].has_growth_signals is True

def test_score_jobs_growth_signals_false_when_absent(full_config):
    jobs = [make_job(description="Stable enterprise company")]
    score_jobs(jobs, full_config)
    assert jobs[0].has_growth_signals is False

def test_score_jobs_em_boosted_by_growth(full_config):
    job_no_growth = make_job(title="Engineering Manager", description="Stable company")
    job_with_growth = make_job(title="Engineering Manager", description="Series B fast-growing")
    score_jobs([job_no_growth, job_with_growth], full_config)
    assert job_with_growth.score_breakdown["title"] > job_no_growth.score_breakdown["title"]

def test_score_jobs_empty_list(full_config):
    result = score_jobs([], full_config)
    assert result == []
