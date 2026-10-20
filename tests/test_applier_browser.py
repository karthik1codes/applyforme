"""Browser regression tests for the Apply interaction layer.

These use local HTML fixtures only.  No real job board is contacted and nothing
is submitted anywhere.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from applyforme.agents import applier as A
from applyforme.apply_state import ApplyState, ApplyStateMachine, LoopDetected
from applyforme.models import Job, Preferences, Profile, Tailored
from applyforme.store import Store


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture()
def page(browser):
    ctx = browser.new_context()
    p = ctx.new_page()
    yield p
    ctx.close()


def test_next_button_with_type_submit_is_not_treated_as_submit(page):
    page.set_content(
        """
        <form>
          <label for="fn">First name</label><input id="fn" name="first_name">
          <button type="submit">Next</button>
        </form>
        """
    )
    kind, label = A._find_action(page, click=False)
    assert kind == "next", (kind, label)
    assert A._click_submit_control(page) is False


def test_real_submit_button_is_detected(page):
    page.set_content(
        """
        <form>
          <input name="first_name" aria-label="First name">
          <button type="submit">Submit application</button>
        </form>
        """
    )
    kind, _ = A._find_action(page, click=False)
    assert kind == "submit"


def test_easy_apply_launcher_is_not_a_form_submit(page):
    page.set_content(
        """
        <main>
          <button>Easy Apply</button>
          <a href="#">Apply on company website</a>
        </main>
        """
    )
    assert A._find_action(page, click=False)[0] is None


def test_modal_scopes_the_action_and_prefers_next(page):
    page.set_content(
        """
        <button>Easy Apply</button>
        <div class="jobs-easy-apply-modal" role="dialog">
          <h3>Contact info</h3>
          <input aria-label="Email">
          <footer><button type="button">Next</button></footer>
        </div>
        """
    )
    kind, label = A._find_action(page, click=False)
    assert kind == "next", (kind, label)


def test_extract_and_fill_a_field_inside_an_iframe(page):
    page.set_content(
        """
        <h1>Application</h1>
        <iframe srcdoc="<label for='em'>Email</label><input id='em' name='email'>"></iframe>
        """
    )
    page.wait_for_timeout(250)
    fields = A.extract_fields(page)
    email = next((f for f in fields if f.label.lower() == "email"), None)
    assert email is not None
    A._fill(page, email, "me@example.com", resume=page, cover_pdf=None)
    assert page.frame_locator("iframe").locator("#em").input_value() == "me@example.com"


def test_custom_aria_dropdown_is_filled(page):
    page.set_content(
        """
        <label id="wa">Work authorization</label>
        <div role="combobox" aria-labelledby="wa" aria-controls="wa-list"
             aria-required="true" tabindex="0">Select</div>
        <ul id="wa-list" role="listbox" style="display:none">
          <li role="option">Yes</li>
          <li role="option">No</li>
        </ul>
        <script>
          const box = document.querySelector('[role=combobox]');
          box.addEventListener('click', () => {
            document.getElementById('wa-list').style.display = 'block';
          });
          document.querySelectorAll('[role=option]').forEach(o => {
            o.addEventListener('click', () => {
              box.textContent = o.textContent;
              box.setAttribute('aria-valuetext', o.textContent);
              document.getElementById('wa-list').style.display = 'none';
            });
          });
        </script>
        """
    )
    fields = A.extract_fields(page)
    combo = next((f for f in fields if f.type == "custom_select"), None)
    assert combo is not None
    A._fill(page, combo, "Yes", resume=page, cover_pdf=None)
    assert page.locator("[role=combobox]").inner_text().strip() == "Yes"


def test_required_validation_is_detected(page):
    page.set_content(
        """
        <form>
          <label for="e">Email *</label>
          <input id="e" name="email" required aria-required="true">
        </form>
        """
    )
    errors, empty = A.validate_form(page)
    assert any("Email" in x for x in empty)
    page.fill("#e", "me@example.com")
    errors, empty = A.validate_form(page)
    assert empty == []


def test_wait_for_change_observes_a_real_step_transition(page):
    page.set_content(
        """
        <form id="f">
          <h3>Step 1</h3>
          <input name="first">
          <button type="button" onclick="setTimeout(() => {
            document.getElementById('f').innerHTML = '<h3>Step 2</h3><input name=last>';
          }, 250)">Next</button>
        </form>
        """
    )
    before = A.step_signature(page)
    page.get_by_role("button", name="Next").click()
    assert A.wait_for_change(page, before, timeout_ms=3000) is True


def test_no_change_after_click_is_detected_and_does_not_wait_forever(page):
    page.set_content("<form><h3>Step 1</h3><button type='button'>Next</button></form>")
    before = A.step_signature(page)
    page.get_by_role("button", name="Next").click()
    assert A.wait_for_change(page, before, timeout_ms=700) is False


def test_verification_requires_explicit_confirmation(page):
    page.set_content("<h1>Thank you for visiting our careers site</h1><p>Back to jobs</p>")
    status, note = A.verify_submission(page, "https://x.test/apply", timeout_s=3)
    assert status == "unverified", note


def test_verification_accepts_explicit_application_confirmation(page):
    page.set_content("<h1>Your application has been submitted</h1><p>We have received your application.</p>")
    status, note = A.verify_submission(page, "https://x.test/apply", timeout_s=3)
    assert status == "applied", note


def test_login_page_after_submit_is_not_a_confirmation(page):
    page.set_content("<h1>Sign in to continue</h1><p>Create an account</p>")
    status, note = A.verify_submission(page, "https://x.test/apply", timeout_s=3)
    assert status == "login", note


def test_stale_dom_reference_can_be_refreshed(page):
    page.set_content("<label for='a'>First name</label><input id='a' name='first_name'>")
    old = A.extract_fields(page)[0]
    page.set_content("<label for='a'>First name</label><input id='a' name='first_name'>")
    with pytest.raises(Exception):
        A._fill(page, old, "Karthik", resume=page, cover_pdf=None)
    fresh = A.extract_fields(page)[0]
    A._fill(page, fresh, "Karthik", resume=page, cover_pdf=None)
    assert page.input_value("#a") == "Karthik"


def test_two_browser_contexts_are_independent(browser):
    c1, c2 = browser.new_context(), browser.new_context()
    try:
        p1, p2 = c1.new_page(), c2.new_page()
        p1.set_content("<input id='x'>")
        p2.set_content("<input id='x'>")
        p1.fill("#x", "one")
        p2.fill("#x", "two")
        assert p1.input_value("#x") == "one"
        assert p2.input_value("#x") == "two"
        assert p1.context is not p2.context
    finally:
        c1.close()
        c2.close()


def test_closed_browser_is_not_treated_as_a_live_page(page):
    page.close()
    assert A._page_alive(page) is False
    assert A.page_signature(page)  # hashes an unavailable page instead of raising


def test_multi_step_form_advances_and_finds_submit(page):
    page.set_content(
        """
        <form id="f">
          <h3>Step 1</h3>
          <label for="fn">First name</label><input id="fn">
          <button type="button" id="next">Next</button>
          <script>
            document.getElementById('next').addEventListener('click', () => {
              document.getElementById('f').innerHTML =
                '<h3>Step 2</h3><label for="ln">Last name</label><input id="ln">' +
                '<button type="button" id="submit">Submit application</button>';
            });
          </script>
        </form>
        """
    )
    before = A.step_signature(page)
    assert A._find_action(page, click=False)[0] == "next"
    A._find_action(page, click=True)
    assert A.wait_for_change(page, before, timeout_ms=3000)
    assert A._find_action(page, click=False)[0] == "submit"


def test_page_signature_changes_after_filling(page):
    page.set_content("<label for='a'>First name</label><input id='a'>")
    before = A.page_signature(page)
    page.fill("#a", "Karthik")
    page.wait_for_timeout(50)
    assert A.page_signature(page) != before


# ---------------------------------------------------------------------------
# End-to-end applier flow against controlled local pages (no network)
# ---------------------------------------------------------------------------

def _profile() -> Profile:
    return Profile(
        personal={
            "first_name": "Karthik",
            "last_name": "M",
            "email": "karm@example.com",
            "phone": "+91 90000 00000",
            "location": "Bengaluru, India",
        },
        resume_path="./resume.pdf",
        screening={"work_authorization": "Yes", "requires_sponsorship": "No"},
        preferences=Preferences(locations=["Bengaluru, India"]),
    )


def _job() -> Job:
    return Job(id="test:acme:1", ats="test", company="Acme", title="Data Engineer", url="https://example.test/apply")


def _ready_machine(store: Store, job_id: str) -> ApplyStateMachine:
    m = ApplyStateMachine(store, job_id)
    if m.terminal:
        return m
    m.start()
    m.transition(ApplyState.JOB_DETAILS_LOADED)
    m.transition(ApplyState.PROFILE_READY)
    m.transition(ApplyState.BROWSER_INITIALIZED)
    return m


def test_apply_in_browser_fills_then_waits_for_explicit_authorization(page, tmp_path, monkeypatch):
    monkeypatch.setenv("APPLYFORME_REVIEW_TIMEOUT_SEC", "1")
    store = Store(tmp_path / "db.sqlite")
    job = _job()
    machine = _ready_machine(store, job.id)
    page.set_content(
        """
        <form>
          <label for="fn">First name</label><input id="fn" required>
          <label for="em">Email</label><input id="em" type="email" required>
          <button type="submit">Submit application</button>
        </form>
        """
    )
    res, note = A._apply_in_browser(
        page, job, _profile(), Tailored(cover_letter="Dear team"),
        resume=Path("resume.pdf"), store=store, dry_run=False,
        auto_submit=False, ask_terminal=False, headed=False,
        skip_initial_goto=True, machine=machine,
    )
    assert res == "awaiting_review", note
    assert page.input_value("#fn") == "Karthik"
    assert page.input_value("#em") == "karm@example.com"
    assert machine.state is ApplyState.AWAITING_USER_REVIEW
    assert not store.submission_recorded(job.id)


def test_apply_in_browser_submits_once_after_authorization(page, tmp_path, monkeypatch):
    monkeypatch.setenv("APPLYFORME_REVIEW_TIMEOUT_SEC", "1")
    store = Store(tmp_path / "db.sqlite")
    job = _job()
    store.authorize_apply(job.id, by="test-user")
    machine = _ready_machine(store, job.id)
    page.set_content(
        """
        <form onsubmit="event.preventDefault(); document.body.innerHTML =
          '<h1>Your application has been submitted</h1><p>We have received your application.</p>';">
          <label for="fn">First name</label><input id="fn" required>
          <label for="em">Email</label><input id="em" type="email" required>
          <button type="submit">Submit application</button>
        </form>
        """
    )
    res, note = A._apply_in_browser(
        page, job, _profile(), Tailored(cover_letter="Dear team"),
        resume=Path("resume.pdf"), store=store, dry_run=False,
        auto_submit=False, ask_terminal=False, headed=False,
        skip_initial_goto=True, machine=machine,
    )
    assert res == "applied", note
    assert machine.state is ApplyState.APPLICATION_CONFIRMED
    assert store.submission_recorded(job.id)

    # A second call must refuse to submit again.
    page.set_content("<button type='submit'>Submit application</button>")
    m2 = _ready_machine(store, job.id)
    res2, note2 = A._apply_in_browser(
        page, job, _profile(), Tailored(cover_letter="Dear team"),
        resume=Path("resume.pdf"), store=store, dry_run=False,
        auto_submit=False, ask_terminal=False, headed=False,
        skip_initial_goto=True, machine=m2,
    )
    assert res2 == "applied", note2
    assert m2.state in (ApplyState.APPLICATION_CONFIRMED, ApplyState.ALREADY_SUBMITTED)


def test_a_next_button_that_never_advances_terminates_as_a_loop(page, tmp_path, monkeypatch):
    monkeypatch.setenv("APPLYFORME_REVIEW_TIMEOUT_SEC", "1")
    original = A.wait_for_change
    monkeypatch.setattr(
        A, "wait_for_change",
        lambda p, before, timeout_ms=8000, machine=None: original(p, before, timeout_ms=250, machine=machine),
    )
    store = Store(tmp_path / "db.sqlite")
    job = _job()
    machine = _ready_machine(store, job.id)
    page.set_content(
        """
        <form>
          <label for="fn">First name</label><input id="fn" required>
          <button type="button">Next</button>
        </form>
        """
    )
    start = time.time()
    with pytest.raises(LoopDetected):
        A._apply_in_browser(
            page, job, _profile(), Tailored(cover_letter="Dear team"),
            resume=Path("resume.pdf"), store=store, dry_run=False,
            auto_submit=False, ask_terminal=False, headed=False,
            skip_initial_goto=True, machine=machine,
        )
    assert time.time() - start < 15
    assert machine.state is ApplyState.FAILED
    assert "loop" in (machine.last_error or "").lower()


def test_multi_step_form_reaches_submit_and_confirms(page, tmp_path, monkeypatch):
    monkeypatch.setenv("APPLYFORME_REVIEW_TIMEOUT_SEC", "1")
    store = Store(tmp_path / "db.sqlite")
    job = _job()
    store.authorize_apply(job.id, by="test-user")
    machine = _ready_machine(store, job.id)
    page.set_content(
        """
        <form id="f">
          <h3>Step 1</h3>
          <label for="fn">First name</label><input id="fn" required>
          <button type="button" id="next">Next</button>
          <script>
            document.getElementById('next').addEventListener('click', () => {
              document.getElementById('f').innerHTML =
                '<h3>Step 2</h3><label for="em">Email</label><input id="em" type="email" required>' +
                '<button type="submit">Submit application</button>';
              document.getElementById('f').addEventListener('submit', (e) => {
                e.preventDefault();
                document.body.innerHTML = '<h1>Your application has been submitted</h1>';
              });
            });
          </script>
        </form>
        """
    )
    res, note = A._apply_in_browser(
        page, job, _profile(), Tailored(cover_letter="Dear team"),
        resume=Path("resume.pdf"), store=store, dry_run=False,
        auto_submit=False, ask_terminal=False, headed=False,
        skip_initial_goto=True, machine=machine,
    )
    assert res == "applied", note
    assert store.submission_recorded(job.id)
