"""Unit tests for models.py"""

from models import Job


def make_job(**kwargs) -> Job:
    defaults = dict(title="Engineering Director", company="Acme",
                    url="https://example.com", source="jsearch")
    return Job(**{**defaults, **kwargs})


# ── _salary_range ────────────────────────────────────────────────

def test_salary_range_min_and_max():
    job = make_job(salary_min=80000, salary_max=120000, salary_currency="GBP")
    assert job._salary_range() == "GBP 80,000 – 120,000"

def test_salary_range_single_value_when_min_equals_max():
    job = make_job(salary_min=91209, salary_max=91209, salary_currency="GBP")
    assert job._salary_range() == "GBP 91,209"

def test_salary_range_single_value_estimated():
    job = make_job(salary_min=91209, salary_max=91209, salary_currency="GBP",
                   salary_is_estimated=True)
    assert job._salary_range() == "GBP 91,209 (estimated)"

def test_salary_range_min_only():
    job = make_job(salary_min=80000, salary_currency="EUR")
    assert job._salary_range() == "EUR 80,000+"

def test_salary_range_no_salary():
    job = make_job()
    assert job._salary_range() == ""

def test_salary_range_estimated_appends_tag():
    job = make_job(salary_min=80000, salary_max=120000, salary_currency="GBP",
                   salary_is_estimated=True)
    assert job._salary_range() == "GBP 80,000 – 120,000 (estimated)"

def test_salary_range_not_estimated_no_tag():
    job = make_job(salary_min=80000, salary_max=120000, salary_currency="GBP",
                   salary_is_estimated=False)
    assert "(estimated)" not in job._salary_range()

def test_salary_range_estimated_min_only():
    job = make_job(salary_min=80000, salary_currency="EUR", salary_is_estimated=True)
    assert job._salary_range() == "EUR 80,000+ (estimated)"


# ── to_dict ──────────────────────────────────────────────────────

def test_to_dict_includes_salary_text():
    job = make_job(salary_text="£90k–120k")
    d = job.to_dict()
    assert d["salary_text"] == "£90k–120k"

def test_to_dict_falls_back_to_salary_range():
    job = make_job(salary_min=80000, salary_max=120000, salary_currency="GBP")
    d = job.to_dict()
    assert "80,000" in d["salary_text"]

def test_to_dict_estimated_tag_in_salary_text():
    job = make_job(salary_min=80000, salary_max=120000, salary_currency="GBP",
                   salary_is_estimated=True)
    d = job.to_dict()
    assert "(estimated)" in d["salary_text"]
