"""Shared fixtures for all tests."""

import pytest

from models import Job


@pytest.fixture
def scoring_cfg():
    """Mirrors config.yaml scoring section exactly."""
    return {
        "title_match": {
            "max_points": 30,
            "exact_director": 30,
            "exact_senior_em": 25,
            "exact_em": 18,
            "founding_cto": 28,
            "partial_match": 10,
        },
        "location_fit": {
            "max_points": 25,
            "prague_onsite_hybrid": 25,
            "emea_remote": 25,
            "worldwide_remote": 22,
            "czech_remote": 20,
            "commute_2hr": 12,
            "commute_4hr": 6,
            "generic_remote": 10,
            "unclear_or_other": 0,
        },
        "company_type": {
            "max_points": 20,
            "product_company": 20,
            "outsourcing": 15,
            "consulting": 8,
            "unknown": 0,
        },
        "seniority": {
            "max_points": 15,
            "director_level": 15,
            "senior_manager": 12,
            "manager": 8,
            "unclear": 0,
        },
        "freshness": {
            "max_points": 10,
            "today": 10,
            "yesterday": 7,
            "two_to_three_days": 4,
            "four_to_seven_days": 2,
        },
        "bonus": {
            "freelancer_friendly": 3,
            "salary_mentioned": 2,
            "growth_signals": 3,
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
