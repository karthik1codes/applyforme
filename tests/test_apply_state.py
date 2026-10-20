"""Regression tests for the deterministic application state machine."""
from __future__ import annotations

import time

import pytest

from applyforme.apply_state import (
    ApplyState,
    ApplyStateError,
    ApplyStateMachine,
    BudgetExceeded,
    Cancelled,
    LoopDetected,
)
from applyforme.models import Job, Profile, Tailored
from applyforme.store import Store


def make_store(tmp_path) -> Store:
    return Store(tmp_path / "test.db")


def test_transition_graph_rejects_skipping_the_form():
    m = ApplyStateMachine(None, "job-1")
    m.start()
    with pytest.raises(ApplyStateError):
        m.transition(ApplyState.APPLICATION_CONFIRMED)


def test_submission_needs_observable_confirmation_evidence():
    m = ApplyStateMachine(None, "job-2")
    m.start()
    m.transition(ApplyState.JOB_DETAILS_LOADED)
    m.transition(ApplyState.PROFILE_READY)
    m.transition(ApplyState.BROWSER_INITIALIZED)
    m.transition(ApplyState.NAVIGATING)
    m.transition(ApplyState.APPLICATION_PAGE_READY)
    m.transition(ApplyState.FORM_DETECTED)
    m.transition(ApplyState.FORM_FILLING)
    m.transition(ApplyState.FORM_VALIDATING)
    m.transition(ApplyState.AWAITING_USER_REVIEW)
    m.transition(ApplyState.SUBMISSION_IN_PROGRESS)
    with pytest.raises(ApplyStateError):
        m.transition(ApplyState.APPLICATION_SUBMITTED)
    m.transition(
        ApplyState.APPLICATION_SUBMITTED,
        evidence={"confirmation": "application received", "errors": False},
    )
    assert m.state is ApplyState.APPLICATION_SUBMITTED


def test_state_survives_a_new_machine_and_steps_are_not_repeated(tmp_path):
    store = make_store(tmp_path)
    m1 = ApplyStateMachine(store, "job-persist")
    m1.start()
    m1.transition(ApplyState.JOB_DETAILS_LOADED)
    m1.transition(ApplyState.PROFILE_READY)
    m1.transition(ApplyState.BROWSER_INITIALIZED)
    m1.transition(ApplyState.NAVIGATING)
    first_steps = m1.step_count

    m2 = ApplyStateMachine(store, "job-persist")
    assert m2.state is ApplyState.NAVIGATING
    assert m2.step_count == first_steps
    m2.resume()
    assert m2.state is ApplyState.BROWSER_INITIALIZED


def test_loop_detection_stops_repeated_identical_observation():
    m = ApplyStateMachine(None, "job-loop", max_identical=3)
    m.start()
    m.observe("same-page")
    m.observe("same-page")
    with pytest.raises(LoopDetected):
        m.observe("same-page")
    assert m.state is ApplyState.FAILED


def test_retry_budget_is_bounded_and_then_fails():
    sleeps: list[float] = []
    now = [0.0]

    def clock() -> float:
        return now[0]

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += max(0.0, seconds)

    m = ApplyStateMachine(None, "job-retry", max_retries=2, sleeper=sleeper, clock=clock)
    m.start()
    m.transition(ApplyState.JOB_DETAILS_LOADED)
    m.transition(ApplyState.PROFILE_READY)
    m.transition(ApplyState.BROWSER_INITIALIZED)
    m.transition(ApplyState.NAVIGATING)
    m.retry("network timeout")
    m.retry("network timeout")
    with pytest.raises(BudgetExceeded):
        m.retry("network timeout")
    assert m.state is ApplyState.FAILED
    assert len(sleeps) >= 2


def test_cancel_is_immediate_and_persisted(tmp_path):
    store = make_store(tmp_path)
    m = ApplyStateMachine(store, "job-cancel")
    m.start()
    store.request_apply_cancel("job-cancel")
    with pytest.raises(Cancelled):
        m.check_cancel()
    assert m.state is ApplyState.CANCELLED
    assert (store.apply_session("job-cancel") or {})["state"] == "CANCELLED"


def test_apply_preflight_honours_a_cancel_request(tmp_path):
    """The preflight must use the Store cancel API, not an old/renamed method."""
    from applyforme.agents.applier import apply

    store = make_store(tmp_path)
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    profile = Profile(personal={}, resume_path=str(resume))
    job = Job(id="test:cancel:1", ats="test", company="Acme", title="Engineer", url="https://example.test/job")
    store.request_apply_cancel(job.id)

    result, note = apply(job, profile, Tailored(cover_letter="hello"), store=store, dry_run=True)

    assert result == "cancelled"
    assert "cancel" in note.lower()
    assert not store.is_apply_cancelled(job.id)


def test_linkedin_postings_keep_the_linkedin_target():
    job = Job(
        id="linkedin:1",
        ats="linkedin",
        company="Acme",
        title="Engineer",
        url="https://www.linkedin.com/jobs/view/1",
        apply_url="https://acme.test/apply",
    )
    assert job.target_url() == "https://www.linkedin.com/jobs/view/1"


def test_non_linkedin_postings_prefer_the_direct_apply_url():
    job = Job(
        id="glassdoor:1",
        ats="glassdoor",
        company="Acme",
        title="Engineer",
        url="https://www.glassdoor.com/job-listing/j?jl=1",
        apply_url="https://acme.test/apply",
    )
    assert job.target_url() == "https://acme.test/apply"


def test_one_worker_owns_an_application_lock(tmp_path):
    store = make_store(tmp_path)
    assert store.acquire_apply_lock("job-lock", "worker-a", ttl_sec=60)
    assert not store.acquire_apply_lock("job-lock", "worker-b", ttl_sec=60)
    store.release_apply_lock("job-lock", "worker-a")
    assert store.acquire_apply_lock("job-lock", "worker-b", ttl_sec=60)


def test_submit_requires_explicit_authorization_and_is_idempotent(tmp_path):
    store = make_store(tmp_path)
    assert not store.apply_submit_authorized("job-submit")
    store.authorize_apply("job-submit", by="test-user")
    assert store.apply_submit_authorized("job-submit")
    assert store.record_submission_attempt("job-submit") is True
    assert store.record_submission_attempt("job-submit") is False  # never click twice
    store.record_submission_confirmed("job-submit", "application received")
    assert store.submission_recorded("job-submit")
    assert not store.apply_submit_authorized("job-submit")


def test_prepare_run_ignores_authorization_left_by_an_older_attempt(tmp_path):
    store = make_store(tmp_path)
    store.authorize_apply("job-floor", by="old-user")
    old = ApplyStateMachine(
        store, "job-floor", submit_authorized_after="2999-01-01T00:00:00+00:00"
    )
    assert not old.authorized_for_submission()
    current = ApplyStateMachine(
        store, "job-floor", submit_authorized_after="2000-01-01T00:00:00+00:00"
    )
    assert current.authorized_for_submission()


def test_authorization_is_consumed_and_never_reused_for_a_retry(tmp_path):
    store = make_store(tmp_path)
    store.authorize_apply("job-retry", by="user")
    assert store.apply_submit_authorized("job-retry")
    assert store.record_submission_attempt("job-retry")
    store.clear_apply_authorization("job-retry")
    assert not store.apply_submit_authorized("job-retry")
    # Clearing authorization must not pretend the submit click never happened.
    assert store.apply_session("job-retry")["submit_attempted_at"]
    assert not store.record_submission_attempt("job-retry")


def test_validation_failure_can_clear_the_attempt_marker(tmp_path):
    store = make_store(tmp_path)
    store.authorize_apply("job-validation", by="test")
    assert store.record_submission_attempt("job-validation")
    store.clear_submission_attempt("job-validation")
    assert store.record_submission_attempt("job-validation") is True


def test_two_jobs_can_be_locked_independently(tmp_path):
    store = make_store(tmp_path)
    assert store.acquire_apply_lock("job-a", "worker-a")
    assert store.acquire_apply_lock("job-b", "worker-b")
    assert not store.acquire_apply_lock("job-a", "worker-b")
    store.release_apply_lock("job-a", "worker-a")
    store.release_apply_lock("job-b", "worker-b")


def test_step_budget_is_enforced():
    m = ApplyStateMachine(None, "job-budget", max_steps=2)
    m.start()  # step 1
    m.transition(ApplyState.JOB_DETAILS_LOADED)  # step 2
    with pytest.raises(BudgetExceeded):
        m.transition(ApplyState.PROFILE_READY)  # step 3 > budget
    assert m.state is ApplyState.FAILED


def test_confirmed_submission_records_evidence_and_blocks_resubmit(tmp_path):
    store = make_store(tmp_path)
    m = ApplyStateMachine(store, "job-confirm")
    m.start()
    m.transition(ApplyState.JOB_DETAILS_LOADED)
    m.transition(ApplyState.PROFILE_READY)
    m.transition(ApplyState.BROWSER_INITIALIZED)
    m.transition(ApplyState.NAVIGATING)
    m.transition(ApplyState.APPLICATION_PAGE_READY)
    m.transition(ApplyState.FORM_DETECTED)
    m.transition(ApplyState.FORM_FILLING)
    m.transition(ApplyState.FORM_VALIDATING)
    store.authorize_apply("job-confirm", by="user")
    assert store.record_submission_attempt("job-confirm")
    m.confirm_submission("Thank you for applying")
    assert m.state is ApplyState.APPLICATION_CONFIRMED
    assert store.submission_recorded("job-confirm")
    assert not store.record_submission_attempt("job-confirm")
