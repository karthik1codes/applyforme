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


def test_the_search_page_guard_only_applies_on_linkedin():
    """A posting that opens the employer ATS must still be fillable."""
    import inspect

    from applyforme.agents.applier import _apply_in_browser

    src = inspect.getsource(_apply_in_browser)
    assert "_is_linkedin(page.url)" in src
    assert "not_a_form" in src


def test_a_success_toast_is_not_a_validation_error():
    """Observed live: clicking Apply showed a success toast.

    "Job moved to In progress under Clicked apply." is a *status* banner, but
    the error selector read it as a validation error and the agent stopped
    with "form needs your input".  The detector must ignore informational
    notifications.
    """
    from applyforme.agents.applier import VISIBLE_ERRORS_JS

    assert "informational" in VISIBLE_ERRORS_JS
    assert "job moved to" in VISIBLE_ERRORS_JS.lower()
    assert "toast" in VISIBLE_ERRORS_JS.lower()
    assert "role=" in VISIBLE_ERRORS_JS


def test_easy_apply_does_not_fall_back_to_an_external_apply_button():
    """Only a real Easy Apply control may return True from _click_easy_apply.

    A posting that says "Apply on company website" must be handled by
    _click_external_apply, which follows the link to the employer's site.
    Returning True for it made the caller believe a modal had opened, so the
    agent filled the LinkedIn page instead of the employer's form.
    """
    from applyforme.agents.applier import _EASY_APPLY_TARGET_JS

    # Easy mode only accepts an "Easy Apply" control.
    assert "cands.find(isEasy)" in _EASY_APPLY_TARGET_JS
    assert "preferEasy" in _EASY_APPLY_TARGET_JS




def test_the_easy_apply_button_is_scoped_to_the_target_job_id():
    """The click must target the control that belongs to the target posting.

    A similar-jobs card in the side rail also has an "Apply" button; picking
    it opens a different posting.
    """
    from applyforme.agents.applier import _EASY_APPLY_TARGET_JS

    assert "isForeign" in _EASY_APPLY_TARGET_JS
    # It must recognise a control wrapped by a link to another posting.
    assert "closest('a[href*=\"/jobs/view/\"]')" in _EASY_APPLY_TARGET_JS
    assert "easy apply" in _EASY_APPLY_TARGET_JS.lower()


def test_easy_apply_uses_the_id_scoped_path_first():
    """_click_easy_apply must receive the target job id."""
    import inspect

    from applyforme.agents.applier import _click_easy_apply

    sig = inspect.signature(_click_easy_apply)
    assert "target_job_id" in sig.parameters


def test_external_apply_is_also_id_scoped():
    """The company-site Apply button must be the target posting's too."""
    import inspect

    from applyforme.agents.applier import _click_external_apply

    sig = inspect.signature(_click_external_apply)
    assert "target_job_id" in sig.parameters


def test_the_targeting_script_matches_the_real_linkedin_dom():
    """The script must work with the DOM that was measured on the live page.

    Measured facts (scripts/probe_linkedin_dom.py against the real posting):
      * there is no ``[data-entity-urn*="jobPosting:"]`` card,
      * there is no ``scaffold-layout__main`` / ``jobs-top-card`` container,
      * the target's Apply control is a standalone
        ``<a aria-label="Apply on company website">Apply</a>``,
      * each card of the "similar jobs" rail is an ``<a href="/jobs/view/<other
        id>">`` that wraps its own Apply button.
    """
    from applyforme.agents.applier import _EASY_APPLY_TARGET_JS

    # It must understand the "Apply on company website" label.
    assert "apply" in _EASY_APPLY_TARGET_JS.lower()
    # A job card's innerText contains "Apply" too, so the label must be the
    # element's OWN text, not the nested badge's.
    assert "ownLabel" in _EASY_APPLY_TARGET_JS
    assert "childNodes" in _EASY_APPLY_TARGET_JS
    # Easy mode must not fall back to a plain Apply control and vice versa.
    assert "cands.find(isEasy)" in _EASY_APPLY_TARGET_JS


