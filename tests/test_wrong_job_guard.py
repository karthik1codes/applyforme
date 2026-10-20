"""Regression tests for the wrong-job guard.

Observed in a live EC2 run on job ``linkedin:li-4479232422`` (Digitap.ai,
"Python Development Internship in Bangalore"):

* After the LinkedIn sign-in the browser sat on a **search-results** page
  whose selected card was a *different* posting.
* Clicking "Easy Apply" matched a card in the **similar-jobs side rail**.
* The search page's "Next" control advanced the carousel, so the job id in
  the URL changed on every wizard step:
  ``4453416357`` -> ``4474260732`` -> ``4479967408`` -> ``4471344068``.

The agent therefore filled the application form of *Sparks To Ideas*
("Python Internship in Ahmedabad", ``4471344068``) instead of the target
posting.  The safety net caught it — the run stopped at
``AWAITING_USER_REVIEW`` and nothing was submitted — but the wrong form was
still filled.  These tests lock down the guard that prevents it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from applyforme.agents.applier import (  # noqa: E402
    _linkedin_job_id,
    _wrong_job_reason,
)
from applyforme.models import Job  # noqa: E402

TARGET_URL = "https://www.linkedin.com/jobs/view/4479232422"


def _job(url: str = TARGET_URL) -> Job:
    return Job(
        id="linkedin:li-4479232422",
        company="Digitap.ai",
        title="Python Development Internship in Bangalore",
        location="Bangalore",
        url=url,
        ats="linkedin",
    )


def test_linkedin_job_id_is_extracted_from_a_job_url():
    assert _linkedin_job_id(TARGET_URL) == "4479232422"


def test_linkedin_job_id_is_extracted_from_a_search_results_url():
    url = (
        "https://www.linkedin.com/jobs/search-results/?currentJobId=4471344068"
        "&keywords=Python%20Development%20Internship%20in%20Bangalore"
        "&origin=JOB_DETAILS_SIMILAR_JOBS_CARD"
    )
    assert _linkedin_job_id(url) == "4471344068"


def test_linkedin_job_id_is_empty_for_a_plain_url():
    assert _linkedin_job_id("https://example.com/jobs") == ""


def test_a_different_job_on_the_page_is_refused():
    """The exact failure from the live run."""
    wrong_url = (
        "https://www.linkedin.com/jobs/search-results/?currentJobId=4471344068"
        "&origin=JOB_DETAILS_SIMILAR_JOBS_CARD"
    )
    reason = _wrong_job_reason(_job(), TARGET_URL, wrong_url)
    assert "different LinkedIn job" in reason
    assert "4471344068" in reason
    assert "4479232422" in reason


def test_every_step_of_the_wrong_carousel_is_refused():
    """Each carousel hop had a different job id; all must be refused."""
    for wrong_id in ("4453416357", "4474260732", "4479967408", "4471344068"):
        url = f"https://www.linkedin.com/jobs/search-results/?currentJobId={wrong_id}"
        assert _wrong_job_reason(_job(), TARGET_URL, url)


def test_the_target_job_itself_is_allowed():
    assert _wrong_job_reason(_job(), TARGET_URL, TARGET_URL) == ""


def test_the_target_job_in_a_search_url_is_allowed():
    url = "https://www.linkedin.com/jobs/search-results/?currentJobId=4479232422"
    assert _wrong_job_reason(_job(), TARGET_URL, url) == ""


def test_a_search_results_page_without_a_selected_card_is_refused():
    url = "https://www.linkedin.com/jobs/search-results/?keywords=python"
    reason = _wrong_job_reason(_job(), TARGET_URL, url)
    assert "search-results" in reason


def test_a_non_linkedin_job_is_never_blocked():
    """Other ATS platforms have no comparable id, so the guard stays out of the way."""
    job = _job("https://boards.greenhouse.io/digitap/jobs/12345")
    assert _wrong_job_reason(job, job.target_url(), "https://boards.greenhouse.io/digitap/jobs/12345") == ""
    assert _wrong_job_reason(job, job.target_url(), "https://boards.greenhouse.io/other/jobs/999") == ""
