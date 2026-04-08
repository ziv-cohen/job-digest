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


# ── from_dict ────────────────────────────────────────────────────

def test_from_dict_roundtrip():
    job = make_job(
        location="Prague, CZ", is_remote=True, remote_region="EMEA",
        seniority="director", company_type="product", score=72.5,
        score_breakdown={"title": 30, "location": 25},
        has_growth_signals=True,
    )
    restored = Job.from_dict(job.to_dict())
    assert restored.title == job.title
    assert restored.company == job.company
    assert restored.score == job.score
    assert restored.seniority == job.seniority
    assert restored.has_growth_signals is True
    assert restored.score_breakdown == {"title": 30, "location": 25}

def test_from_dict_missing_optional_fields():
    d = {"title": "CTO", "company": "Startup", "url": "https://x.com", "source": "remotive"}
    job = Job.from_dict(d)
    assert job.title == "CTO"
    assert job.location == ""
    assert job.score == 0.0
    assert job.has_growth_signals is False

def test_from_dict_parses_date_posted():
    job = make_job()
    d = job.to_dict()
    d["date_posted"] = "2026-04-01T08:00:00+00:00"
    restored = Job.from_dict(d)
    assert restored.date_posted is not None
    assert restored.date_posted.year == 2026

def test_from_dict_empty_date_posted():
    d = {"title": "EM", "company": "Co", "url": "https://x.com", "source": "jsearch",
         "date_posted": ""}
    job = Job.from_dict(d)
    assert job.date_posted is None
