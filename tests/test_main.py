"""Unit tests for helper functions in main.py."""

from models import Job
from main import _salary_above_minimum


MIN_SALARY = {
    "CZK": 2400000,
    "EUR": 95000,
    "USD": 100000,
    "GBP": 80000,
    "PLN": 400000,
}


def make_job(**kwargs) -> Job:
    defaults = dict(title="Engineering Director", company="Acme", url="https://example.com", source="jsearch")
    return Job(**{**defaults, **kwargs})


# ── No salary info → always keep ──────────────────────────────────

def test_no_salary_max_keeps_job():
    job = make_job(salary_max=None, salary_currency=None)
    assert _salary_above_minimum(job, MIN_SALARY) is True

def test_no_currency_keeps_job():
    job = make_job(salary_max=90000, salary_currency=None)
    assert _salary_above_minimum(job, MIN_SALARY) is True

def test_unknown_currency_keeps_job():
    job = make_job(salary_max=50000, salary_currency="CHF")
    assert _salary_above_minimum(job, MIN_SALARY) is True


# ── GBP ───────────────────────────────────────────────────────────

def test_gbp_above_threshold_passes():
    job = make_job(salary_max=90000, salary_currency="GBP")
    assert _salary_above_minimum(job, MIN_SALARY) is True

def test_gbp_at_threshold_passes():
    job = make_job(salary_max=80000, salary_currency="GBP")
    assert _salary_above_minimum(job, MIN_SALARY) is True

def test_gbp_below_threshold_filtered():
    job = make_job(salary_max=60000, salary_currency="GBP")
    assert _salary_above_minimum(job, MIN_SALARY) is False

def test_gbp_very_low_filtered():
    job = make_job(salary_max=40000, salary_currency="GBP")
    assert _salary_above_minimum(job, MIN_SALARY) is False


# ── EUR ───────────────────────────────────────────────────────────

def test_eur_above_threshold_passes():
    job = make_job(salary_max=120000, salary_currency="EUR")
    assert _salary_above_minimum(job, MIN_SALARY) is True

def test_eur_below_threshold_filtered():
    job = make_job(salary_max=70000, salary_currency="EUR")
    assert _salary_above_minimum(job, MIN_SALARY) is False


# ── USD ───────────────────────────────────────────────────────────

def test_usd_above_threshold_passes():
    job = make_job(salary_max=150000, salary_currency="USD")
    assert _salary_above_minimum(job, MIN_SALARY) is True

def test_usd_below_threshold_filtered():
    job = make_job(salary_max=80000, salary_currency="USD")
    assert _salary_above_minimum(job, MIN_SALARY) is False


# ── CZK ───────────────────────────────────────────────────────────

def test_czk_above_threshold_passes():
    job = make_job(salary_max=3000000, salary_currency="CZK")
    assert _salary_above_minimum(job, MIN_SALARY) is True

def test_czk_below_threshold_filtered():
    job = make_job(salary_max=1800000, salary_currency="CZK")
    assert _salary_above_minimum(job, MIN_SALARY) is False


# ── Currency casing ───────────────────────────────────────────────

def test_lowercase_currency_normalised():
    job = make_job(salary_max=40000, salary_currency="gbp")
    assert _salary_above_minimum(job, MIN_SALARY) is False

def test_currency_with_spaces_normalised():
    job = make_job(salary_max=40000, salary_currency=" GBP ")
    assert _salary_above_minimum(job, MIN_SALARY) is False
