"""Shared fixtures for all tests."""

import pytest

from models import Job


@pytest.fixture
def scoring_cfg():
    """Mirrors config.yaml scoring section exactly."""
    return {
        "weights": {
            "profile_match": 45,
            "title": 15,
            "location": 15,
            "company_type": 10,
            "seniority": 5,
            "freshness": 5,
            "conditions": 5,
        },
        "title_match": {
            "founding_cto": 100,
            "exact_cto": 90,
            "exact_vp": 100,
            "exact_director": 100,
            "exact_senior_em": 85,
            "exact_em": 60,
            "em_growth_boost": 15,
            "partial_match": 35,
        },
        "location_fit": {
            "prague_onsite_hybrid": 100,
            "emea_remote": 100,
            "worldwide_remote": 90,
            "czech_remote": 80,
            "commute_2hr": 50,
            "commute_4hr": 25,
            "generic_remote": 40,
            "unclear_or_other": 0,
        },
        "company_type": {
            "product_company": 100,
            "outsourcing": 75,
            "consulting": 40,
            "unknown": 0,
        },
        "seniority": {
            "cto_level": 100,
            "vp_level": 100,
            "director_level": 100,
            "senior_manager": 80,
            "manager": 55,
            "unclear": 0,
        },
        "freshness": {
            "today": 100,
            "yesterday": 70,
            "two_to_three_days": 40,
            "four_to_seven_days": 20,
        },
        "conditions": {
            "freelancer_friendly": 40,
            "salary_mentioned": 25,
            "growth_signals": 35,
        },
        "min_score": 40,
    }


@pytest.fixture
def full_config(scoring_cfg):
    return {
        "api_keys": {
            "jsearch_rapidapi_key": "test-key",
            "adzuna_app_id": "test-id",
            "adzuna_app_key": "test-key",
        },
        "email": {
            "smtp_server": "smtp.example.com",
            "smtp_port": 587,
            "sender_email": "test@example.com",
            "sender_password": "password",
            "recipient_email": "me@example.com",
        },
        "search": {
            "role_titles": [
                "engineering director",
                "senior engineering manager",
                "engineering manager",
                "director of engineering",
                "VP engineering",
                "head of engineering",
                "founding CTO",
            ],
            "locations": {
                "primary_city": "Prague",
                "country": "Czech Republic",
                "region": "EMEA",
            },
            "max_age_days": 7,
        },
        "scoring": scoring_cfg,
        "output": {"max_jobs_in_digest": 0},
    }


def make_job(**kwargs) -> Job:
    defaults = dict(
        title="Engineering Manager",
        company="Acme",
        url="https://example.com/job/1",
        source="jsearch",
    )
    return Job(**{**defaults, **kwargs})
