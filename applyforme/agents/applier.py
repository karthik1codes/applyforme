"""Applier agent: opens the application form in a real browser, maps fields -> profile answers
with an LLM, fills them, then WAITS for human approval before submitting.

Browser is headed by default so you can watch/interact like a normal user. Live screenshots
are written for the dashboard (`data/apply-live.png` + `data/apply-live.json`).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright
from pydantic import BaseModel

from ..apply_state import (
    ApplyState,
    ApplyStateError,
    ApplyStateMachine,
    BudgetExceeded,
    Cancelled,
    LoopDetected,
)
from ..config import DATA_DIR, ROOT
from ..browser_runtime import (
    ensure_playwright_browsers_path,
    kill_stale_apply_browsers,
    prepare_local_browser,
)
from ..captcha import captcha_solved_on_page, detect_captcha, wait_for_manual_captcha
from ..field_map import map_fields, unknown_required
from ..firecrawl_browser import apply_engine, firecrawl_enabled
from ..llm import ask_json
from ..models import FieldAnswer, FormField, Job, Profile, Tailored
from ..store import Store
from .routing import (
    classify_submission,
    closed_reason,
    has_submit_control,
    is_confirmation_text,
    manual_reason,
)

LIVE_PNG = DATA_DIR / "apply-live.png"
LIVE_JSON = DATA_DIR / "apply-live.json"


def _can_prompt() -> bool:
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        return False


def _headed() -> bool:
    """Show a real Chromium window (default on). Set APPLYFORME_BROWSER_HEADED=0 for headless."""
    return os.getenv("APPLYFORME_BROWSER_HEADED", "1").strip().lower() not in ("0", "false", "no", "off")


def _slow_mo_ms() -> int:
    try:
        return max(0, int(os.getenv("APPLYFORME_BROWSER_SLOW_MO", "80")))
    except ValueError:
        return 80


def _captcha_manual_sec() -> int:
    """Extra time to wait for manual captcha when auto-solve is off or fails."""
    try:
        return max(0, int(os.getenv("APPLYFORME_CAPTCHA_WAIT_SEC", "120")))
    except ValueError:
        return 120


def _live_writer(job: Job, page: Page | None):
    def _w(phase: str, detail: str) -> None:
        _write_live(job, page, phase, detail)

    return _w


def _prepare_captcha_for_submit(page: Page, job: Job, deadline: float | None = None) -> tuple[bool, str]:
    """CAPTCHAs are solved by the human in the visible browser, never by us.

    The previous implementation optionally sent the challenge to a third-party
    solver.  That bypasses the site's bot protection and is intentionally
    disabled: we pause, explain what is needed, and resume only after the page
    itself reports the challenge cleared.
    """
    live = _live_writer(job, page)
    if not detect_captcha(page):
        return True, "no captcha"
    wait = _captcha_manual_sec()
    if deadline is not None:
        wait = min(wait, int(_deadline_left(deadline)))
    message = "A CAPTCHA is present. Solve it in the Chromium window; the agent will not bypass it."
    if wait > 0 and _headed():
        print(f"[applier] captcha needs you — {wait}s to solve in the browser window")
        live("captcha", f"Solve the CAPTCHA in the browser ({wait}s)")
        if wait_for_manual_captcha(page, wait, live=live):
            return True, "captcha solved manually"
    if detect_captcha(page) and not captcha_solved_on_page(page):
        return False, message
    return True, "captcha cleared"


def _watch_seconds() -> int:
    """Dry-run only: how long to leave the filled form visible for inspection."""
    try:
        return max(0, int(os.getenv("APPLYFORME_APPLY_WATCH_SEC", "45")))
    except ValueError:
        return 45


def _apply_timeout_sec() -> int:
    """Hard ceiling for one Apply attempt; browser closes when exceeded."""
    try:
        return max(45, int(os.getenv("APPLYFORME_APPLY_TIMEOUT_SEC", "180")))
    except ValueError:
        return 180


def _review_timeout_sec() -> int:
    """How long a prepared application waits for explicit submit authorization."""
    try:
        return max(30, int(os.getenv("APPLYFORME_REVIEW_TIMEOUT_SEC", "600")))
    except ValueError:
        return 600


def _max_apply_steps() -> int:
    try:
        return max(10, int(os.getenv("APPLYFORME_MAX_APPLY_STEPS", "80")))
    except ValueError:
        return 80


def _wait_for_authorization(
    machine: ApplyStateMachine, store, *, timeout_sec: int, deadline: float | None = None
) -> bool:
    """Wait for the dashboard's explicit submit authorization (or cancel)."""
    end = time.time() + timeout_sec
    if deadline is not None:
        end = min(end, deadline)
    while time.time() < end:
        machine.check_cancel()
        if machine.submission_already_recorded():
            return False
        if machine.authorized_for_submission():
            return True
        time.sleep(1)
    return False


def _deadline_left(deadline: float | None) -> float:
    if deadline is None:
        return 1e9
    return max(0.0, deadline - time.time())


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.time() >= deadline:
        raise TimeoutError(
            f"apply timed out after {_apply_timeout_sec()}s — closing browser (raise APPLYFORME_APPLY_TIMEOUT_SEC to allow longer)"
        )


def _page_alive(page: Page | None) -> bool:
    if page is None:
        return False
    try:
        if page.is_closed():
            return False
        _ = page.url
        return True
    except Exception:
        return False


def _safe_screenshot(page: Page | None, path: Path, *, full_page: bool = False) -> bool:
    if not _page_alive(page):
        return False
    try:
        page.screenshot(path=str(path), full_page=full_page)  # type: ignore[union-attr]
        return True
    except Exception as e:
        msg = str(e).lower()
        if "has been closed" in msg or "target page" in msg or "browser has been closed" in msg:
            return False
        print(f"[applier] screenshot skipped: {e}")
        return False


def _write_live(
    job: Job,
    page: Page | None,
    phase: str,
    note: str = "",
    *,
    live_view_url: str = "",
    engine: str = "",
) -> None:
    """Snapshot for the dashboard live viewer (PNG and/or Firecrawl liveView iframe)."""
    prev: dict = {}
    try:
        if LIVE_JSON.exists():
            prev = json.loads(LIVE_JSON.read_text(encoding="utf-8"))
    except Exception:
        prev = {}
    payload = {
        "job_id": job.id,
        "company": job.company,
        "title": job.title,
        "phase": phase,
        "note": note,
        "url": "",
        "updated_at": time.time(),
        "headed": _headed(),
        "engine": engine or prev.get("engine") or apply_engine(),
        "live_view_url": live_view_url or prev.get("live_view_url") or "",
    }
    if _page_alive(page):
        try:
            payload["url"] = page.url  # type: ignore[union-attr]
        except Exception:
            pass
        _safe_screenshot(page, LIVE_PNG, full_page=False)
    try:
        LIVE_JSON.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass


def _watch_filled_form(page: Page, job: Job, seconds: int, deadline: float | None = None) -> None:
    """Keep the browser open so the user can watch / fix captchas / edit fields."""
    if seconds <= 0:
        return
    if deadline is not None:
        seconds = min(seconds, int(_deadline_left(deadline)))
        if seconds <= 0:
            _check_deadline(deadline)
            return
    print(f"[applier] watching for {seconds}s — Chromium window is yours; fix captchas or fields if needed")
    end = time.time() + seconds
    while time.time() < end:
        _check_deadline(deadline)
        if not _page_alive(page):
            print("[applier] watch stopped — browser already closed")
            return
        left = int(end - time.time())
        _write_live(job, page, "watching", f"{left}s left to review (nothing is submitted automatically)")
        try:
            page.wait_for_timeout(min(2000, max(200, int((end - time.time()) * 1000))))
        except Exception:
            return


def _is_linkedin(url: str) -> bool:
    return "linkedin.com" in (url or "").lower()


def _linkedin_login_sec() -> int:
    try:
        return max(90, int(os.getenv("APPLYFORME_LINKEDIN_LOGIN_SEC", "300")))
    except ValueError:
        return 300


def _linkedin_needs_auth(page: Page) -> bool:
    """True when LinkedIn is asking the user to sign in (URL wall OR modal overlay)."""
    import re

    u = (page.url or "").lower()
    if any(x in u for x in ("/login", "/uas/", "/checkpoint/", "authwall", "/signup")):
        return True
    try:
        body = page.evaluate("() => (document.body && document.body.innerText || '').slice(0, 5000)")
    except Exception:
        body = ""
    bl = (body or "").lower()
    auth_phrases = (
        "sign in to see who you already know",
        "sign in to view more jobs",
        "sign in to continue",
        "welcome back",
        "sign in with email",
        "new to linkedin?",
    )
    if any(p in bl for p in auth_phrases):
        # Avoid false positive on logged-in pages that mention "sign in" in footer copy
        if "continue with google" in bl or "sign in with email" in bl or "join now" in bl:
            return True
    try:
        # Guest header: top-right Sign in, no profile menu
        sign_in = page.get_by_role("link", name=re.compile(r"^sign in$", re.I))
        me = page.locator(
            "img.global-nav__me-photo, button.global-nav__primary-link-me-menu-trigger, "
            ".global-nav__me, [data-global-nav-link='me']"
        )
        if sign_in.count() and sign_in.first.is_visible() and me.count() == 0:
            return True
    except Exception:
        pass
    try:
        modal = page.locator(
            "[data-test-modal], .sign-in-modal, .authwall, "
            "div[role='dialog']:has-text('Sign in'), div[role='dialog']:has-text('Continue with Google')"
        )
        if modal.count() and modal.first.is_visible():
            return True
    except Exception:
        pass
    return False


def _nudge_linkedin_email_signin(page: Page) -> None:
    """Open the email/password form (not Continue with Google)."""
    import re

    for pattern in (
        re.compile(r"sign in with email", re.I),
        re.compile(r"^sign in$", re.I),
    ):
        for role in ("button", "link"):
            loc = page.get_by_role(role, name=pattern)
            try:
                if loc.count() and loc.first.is_visible():
                    label = (loc.first.inner_text() or "").lower()
                    if "google" in label:
                        continue
                    loc.first.click(timeout=4000)
                    page.wait_for_timeout(1000)
                    return
            except Exception:
                continue


def _wait_linkedin_login(
    page: Page, job: Job, *, force: bool = False, deadline: float | None = None
) -> bool:
    """Wait for the user to sign in to LinkedIn in the visible Chromium window.

    We deliberately do **not** ask for or store the user's LinkedIn password, and
    we do not inject session cookies.  LinkedIn's own login, 2FA, passkey and
    CAPTCHA flows stay entirely in LinkedIn's page.  The persistent browser
    profile keeps the resulting session for the next Apply.
    """
    if not force and not _linkedin_needs_auth(page):
        return True
    if not _headed() and not firecrawl_enabled():
        msg = (
            "LinkedIn sign-in required — this worker runs headless, so there is no window "
            "to sign in. Use a Firecrawl live-view session or sign in once in a headed "
            "browser; the agent will reuse that profile."
        )
        print(f"[applier] {msg}")
        _write_live(job, page, "linkedin_login", msg)
        return False
    secs = _linkedin_login_sec()
    if deadline is not None:
        secs = min(secs, max(15, int(_deadline_left(deadline))))
    print(f"[applier] LinkedIn sign-in required — finish it in the Chromium window ({secs}s)")
    _write_live(
        job,
        page,
        "linkedin_login",
        "Sign in to LinkedIn in this window (including any 2FA). The agent never stores your password.",
    )
    _nudge_linkedin_email_signin(page)

    end = time.time() + secs
    while time.time() < end:
        _check_deadline(deadline)
        try:
            page.bring_to_front()
        except Exception:
            pass
        if not _linkedin_needs_auth(page):
            print("[applier] LinkedIn session ready")
            _write_live(job, page, "linkedin_ok", "Logged in — continuing apply")
            page.wait_for_timeout(1500)
            return True
        left = int(end - time.time())
        _write_live(job, page, "linkedin_login", f"Waiting for LinkedIn sign-in to finish… {left}s")
        page.wait_for_timeout(2000)
    return False


def _click_easy_apply(page: Page) -> bool:
    """Open LinkedIn Easy Apply modal only (not external company Apply)."""
    import re

    candidates = [
        page.get_by_role("button", name=re.compile(r"easy apply", re.I)),
        page.get_by_role("link", name=re.compile(r"easy apply", re.I)),
        page.locator("button[aria-label*='Easy Apply' i]"),
        page.locator("button.jobs-apply-button:has-text('Easy Apply')"),
    ]
    for loc in candidates:
        try:
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=5000)
                page.wait_for_timeout(2000)
                return True
        except Exception:
            continue
    return False


def _click_external_apply(page: Page) -> bool:
    """Company-site Apply (opens external ATS). Returns True if a new navigation/tab likely started."""
    import re

    # Prefer buttons that are NOT Easy Apply
    locs = [
        page.get_by_role("button", name=re.compile(r"^\s*apply\s*$", re.I)),
        page.get_by_role("link", name=re.compile(r"^\s*apply\s*$", re.I)),
        page.locator("a.jobs-apply-button, button.jobs-apply-button"),
    ]
    before = list(page.context.pages)
    for loc in locs:
        try:
            if not loc.count() or not loc.first.is_visible():
                continue
            text = ((loc.first.inner_text() or "") + " " + (loc.first.get_attribute("aria-label") or "")).lower()
            if "easy apply" in text:
                continue
            loc.first.click(timeout=5000)
            page.wait_for_timeout(2500)
            # New tab?
            after = page.context.pages
            if len(after) > len(before):
                after[-1].bring_to_front()
            return True
        except Exception:
            continue
    return False


def _scroll_form_footer(page: Page) -> None:
    """Bring Easy Apply / ATS footers into view so primary actions are visible."""
    try:
        page.evaluate(
            """() => {
              const roots = [
                document.querySelector('.jobs-easy-apply-modal'),
                document.querySelector('.jobs-easy-apply-content'),
                document.querySelector('[data-test-modal-id]'),
                document.querySelector('.artdeco-modal__content'),
                document.querySelector('form'),
                document.scrollingElement,
              ].filter(Boolean);
              for (const el of roots) {
                try { el.scrollTop = el.scrollHeight; } catch (_) {}
                try { el.scrollTo?.(0, el.scrollHeight || 1e9); } catch (_) {}
              }
              const footer = document.querySelector(
                'footer.jobs-easy-apply-footer, .jobs-easy-apply-modal footer, .artdeco-modal__actionbar, form footer'
              );
              footer?.scrollIntoView?.({ block: 'end', inline: 'nearest' });
            }"""
        )
    except Exception:
        pass


def _try_click_loc(loc, *, timeout: int = 5000) -> bool:
    try:
        if not loc.count():
            return False
        el = loc.first
        if not el.is_visible():
            return False
        try:
            el.scroll_into_view_if_needed(timeout=1500)
        except Exception:
            pass
        # LinkedIn often keeps Submit disabled until blur; wait briefly then force.
        try:
            el.click(timeout=timeout)
        except Exception:
            el.click(timeout=timeout, force=True)
        return True
    except Exception:
        return False


_ACTION_JS = r"""
(token) => {
  const vis = el => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !el.disabled;
  };
  const txt = el => ((el.innerText || el.value || '') + ' ' + (el.getAttribute('aria-label') || '')
    + ' ' + (el.getAttribute('data-control-name') || '')).replace(/\s+/g, ' ').trim().toLowerCase();
  const hasModal = !!document.querySelector('.jobs-easy-apply-modal, div[role="dialog"]');
  const inForm = el => !!el.closest('form');
  const classify = (label, el) => {
    if (!label) return null;
    if (/(dismiss|cancel|close|discard|unfollow|save|follow|message|share)/.test(label)) return null;
    if (/easy apply|apply with|apply on company|company website/.test(label) && !hasModal) return null;
    if (/(submit|send).*(application)|^submit$|^finish$|done applying|submit application|send application/.test(label)) return 'submit';
    if (/^(next|continue|review|save and continue|save)$/.test(label)) return 'next';
    if (/(continue to next step|review your application|next step)/.test(label)) return 'next';
    if (/(next|continue)/.test(label) && !/submit/.test(label)) return 'next';
    if (/^apply$|^apply now$|^send$/.test(label) && inForm(el)) return 'submit';
    return null;
  };
  const nodes = [...document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"]')]
    .filter(el => vis(el) && !el.hasAttribute('data-afm-skip'));
  const seen = new Set();
  const out = [];
  for (const el of nodes) {
    // Prefer controls inside the open modal; ignore the page behind it.
    if (hasModal && !el.closest('.jobs-easy-apply-modal, div[role="dialog"], footer')) {
      const modal = document.querySelector('.jobs-easy-apply-modal, div[role="dialog"]');
      if (modal && !modal.contains(el)) continue;
    }
    const label = txt(el);
    const kind = classify(label, el);
    if (!kind) continue;
    const key = kind + '|' + label;
    if (seen.has(key)) continue;
    seen.add(key);
    if (kind === 'submit') {
      const tag = token + '-submit';
      el.setAttribute('data-afm-submit', tag);
      out.push({kind, label, tag});
      break;
    }
    if (!out.some(o => o.kind === 'next')) {
      const tag = token + '-next';
      el.setAttribute('data-afm-next', tag);
      out.push({kind, label, tag});
    }
  }
  return out;
}
"""


def _classify_control(label: str, *, in_form: bool = False, modal_open: bool = False) -> str | None:
    """Pure classifier used by tests and the browser-side action finder."""
    l = re.sub(r"\s+", " ", (label or "").lower()).strip()
    if not l:
        return None
    if re.search(r"\b(dismiss|cancel|close|discard|unfollow|save|follow|message|share)\b", l):
        return None
    if not modal_open and re.search(r"easy apply|apply with|apply on company|company website", l):
        return None
    if re.search(r"(submit|send).*application|^submit$|^finish$|done applying|submit application|send application", l):
        return "submit"
    if re.fullmatch(r"(next|continue|review|save and continue|save)", l):
        return "next"
    if re.search(r"continue to next step|review your application|next step", l):
        return "next"
    if re.search(r"\b(next|continue)\b", l) and "submit" not in l:
        return "next"
    if in_form and re.fullmatch(r"(apply|apply now|send)", l):
        return "submit"
    return None


def _find_action(page: Page, *, click: bool = False) -> tuple[str | None, str]:
    """Find the current wizard control. Returns (kind, label).

    ``type=submit`` is deliberately **not** treated as submit on its own: many
    ATS forms use ``<button type="submit">Next</button>``.  The visible label is
    the source of truth.  This was the main cause of the apply loop.
    """
    _scroll_form_footer(page)
    token = "afm" + uuid.uuid4().hex[:10]
    try:
        found = page.evaluate(_ACTION_JS, token) or []
    except Exception:
        found = []
    if not found:
        return None, ""
    chosen = next((x for x in found if x.get("kind") == "submit"), None) or found[0]
    kind = chosen.get("kind")
    attr = "data-afm-submit" if kind == "submit" else "data-afm-next"
    tag = chosen.get("tag")
    if click:
        loc = page.locator(f'[{attr}="{tag}"]')
        if not _try_click_loc(loc, timeout=6000):
            return None, str(chosen.get("label") or "")
        try:
            page.wait_for_timeout(350)
        except Exception:
            pass
    return kind, str(chosen.get("label") or "")


def _easy_apply_action(page: Page, *, click: bool = True) -> str | None:
    kind, _ = _find_action(page, click=click)
    return kind


def _click_submit_control(page: Page) -> bool:
    """Click a submit control, never a Next/Continue control."""
    _scroll_form_footer(page)
    kind, label = _find_action(page, click=False)
    if kind != "submit":
        print(f"[applier] submit blocked: current control is {kind or 'unknown'!r} ({label!r})")
        return False
    kind2, _ = _find_action(page, click=True)
    return kind2 == "submit"


def _easy_apply_click_next(page: Page) -> str | None:
    return _easy_apply_action(page, click=True)


def _easy_apply_modal_open(page: Page) -> bool:
    """True when LinkedIn Easy Apply dialog is visible."""
    import re

    try:
        dlg = page.locator(
            ".jobs-easy-apply-modal, div.artdeco-modal.jobs-easy-apply-modal, "
            "div[role='dialog']"
        )
        if not dlg.count():
            return False
        text = (dlg.first.inner_text(timeout=1500) or "").lower()
        return any(x in text for x in ("easy apply", "upload resume", "submit application", "resume", "next"))
    except Exception:
        try:
            return bool(page.locator(".jobs-easy-apply-modal").count())
        except Exception:
            return False


def _upload_tailored_resume(page: Page, resume: Path) -> bool:
    """LinkedIn Easy Apply lists old PDFs as radios — upload the tailored file instead.

    The file input is often hidden until 'Upload resume' is clicked; Playwright can still
    set_input_files on hidden inputs once the control exists.
    """
    import re

    if not resume.exists():
        return False

    # If the page already has the file selected (including after a re-render),
    # do not upload it again: re-uploading resets the site's own resume choice
    # and was one of the repeated actions in the old loop.
    try:
        has_file = page.evaluate(
            """() => [...document.querySelectorAll('input[type=file]')]
                 .some(i => i.files && i.files.length > 0)"""
        )
        if has_file:
            return True
    except Exception:
        pass

    roots = [
        page.locator(".jobs-easy-apply-modal"),
        page.locator("div[role='dialog']"),
        page.locator("body"),
    ]
    for root in roots:
        try:
            if not root.count():
                continue
        except Exception:
            continue

        # Reveal / focus LinkedIn's document upload control
        for loc in (
            root.get_by_role("button", name=re.compile(r"upload resume", re.I)),
            root.locator("button:has-text('Upload resume'), label:has-text('Upload resume')"),
            root.locator("[aria-label*='Upload resume' i], [data-test-job-apply-flow] label"),
        ):
            try:
                if loc.count() and loc.first.is_visible():
                    _try_click_loc(loc, timeout=3500)
                    page.wait_for_timeout(600)
                    break
            except Exception:
                continue

        inputs = root.locator("input[type='file']")
        try:
            n = inputs.count()
        except Exception:
            n = 0
        for i in range(n):
            inp = inputs.nth(i)
            try:
                accept = (inp.get_attribute("accept") or "").lower()
                if accept and not any(x in accept for x in ("pdf", "doc", "word", "*")):
                    continue
                inp.set_input_files(str(resume))
                page.wait_for_timeout(1800)
                # Prefer the newly uploaded card (often first / checked after upload)
                try:
                    fresh = root.locator(
                        f"label:has-text('{resume.name}'), "
                        "div.jobs-document-upload-redesign-card:has(input:checked)"
                    )
                    if fresh.count():
                        _try_click_loc(fresh.first, timeout=2000)
                except Exception:
                    pass
                print(f"[applier] uploaded tailored resume → {resume.name}")
                return True
            except Exception as e:
                print(f"[applier] resume upload attempt failed: {e}")
    return False


def _fill_visible_fields(
    page: Page,
    job: Job,
    profile: Profile,
    tailored: Tailored,
    resume: Path,
    store,
    ask_terminal: bool,
    answer_cache: dict[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """Fill the current form step.

    Deterministic profile mapping runs first; the LLM is asked only about the
    fields that remain.  Values already present in the control are left alone,
    so re-entering a step does not rewrite the same answers or re-trigger
    validation loops.
    """
    fields = extract_fields(page)
    print(f"[applier] found {len(fields)} fields on this step")
    if not fields:
        return None, None

    answer_cache = answer_cache if answer_cache is not None else {}
    saved = store.get_answers(job.id) if store else {}
    deterministic = map_fields(fields, profile, tailored)

    unknown = [f for f in fields if f.key not in deterministic]
    llm_answers: dict[str, FieldAnswer] = {}
    if unknown:
        still_unknown: list[FormField] = []
        for f in unknown:
            cache_key = _field_cache_key(f)
            if cache_key in answer_cache:
                llm_answers[f.key] = FieldAnswer(
                    key=f.key, value=answer_cache[cache_key], confidence=0.7, source="llm"
                )
            else:
                still_unknown.append(f)
        if still_unknown:
            try:
                for a in plan_answers(still_unknown, job, profile, tailored):
                    if a.value not in (None, ""):
                        llm_answers[a.key] = a
                        match = next((f for f in still_unknown if f.key == a.key), None)
                        if match is not None:
                            answer_cache[_field_cache_key(match)] = str(a.value)
            except Exception as e:
                print(f"[applier] LLM field mapping failed: {e}")

    answers: dict[str, FieldAnswer] = {**llm_answers, **deterministic}
    resolved: list[tuple[FormField, str]] = []
    pending: list[tuple[FormField, str | None]] = []
    for f in fields:
        a = answers.get(f.key)
        value = a.value if a else None
        uncertain = value is None or (a is not None and a.confidence < 0.5 and f.type != "file")
        if uncertain:
            if f.label in saved:
                value = saved[f.label]
            elif not _is_required(f):
                continue
            elif ask_terminal:
                hint = f" options={f.options}" if f.options else ""
                value = input(
                    f"\n[needs you] {f.label!r} ({f.type}){hint}\n  suggested={value!r}\n  your answer (Enter=skip): "
                ).strip() or value
            else:
                pending.append((f, value))
                continue
        if value not in (None, ""):
            resolved.append((f, str(value)))

    if pending and store:
        store.save_questions(
            job.id,
            [{"label": f.label, "type": f.type, "options": f.options, "suggested": v} for f, v in pending],
        )
        store.add_event(
            job.id,
            "needs_feedback",
            f"{len(pending)} question(s) need your answer",
            "; ".join(f.label for f, _ in pending)[:500],
        )
        return "needs_feedback", "waiting for your answers on the dashboard"

    failures: list[str] = []
    for f, value in resolved:
        if _already_filled(f, value):
            continue
        try:
            _fill(page, f, value, resume, None)
            if not _verify_field(page, f, value):
                failures.append(f.label or f.key)
        except Exception as e:
            try:
                refreshed = extract_fields(page)
                match = next((x for x in refreshed if _same_field(x, f)), None)
                if match is None:
                    raise
                _fill(page, match, value, resume, None)
                if not _verify_field(page, match, value):
                    failures.append(f.label or f.key)
            except Exception as e2:
                print(f"[applier] could not fill {f.label!r}: {e2}")
                failures.append(f.label or f.key)

    if failures:
        note = "could not fill: " + "; ".join(dict.fromkeys(failures))[:400]
        return "fill_errors", note
    return None, None


def _field_cache_key(f: FormField) -> str:
    from ..field_map import norm

    return norm(" ".join(x for x in (f.label, f.name, f.element_id) if x))


def _same_field(a: FormField, b: FormField) -> bool:
    return _field_cache_key(a) == _field_cache_key(b) and a.type == b.type


def _already_filled(f: FormField, value: str) -> bool:
    if f.type == "file":
        return False
    if f.type in ("radio", "checkbox"):
        return bool(f.checked) and norm_equals(f.current, value)
    if f.current and norm_equals(f.current, value):
        return True
    return False


def norm_equals(a: str, b: str) -> bool:
    from ..field_map import norm

    return norm(a) == norm(b)


def _verify_field(page: Page, f: FormField, value: str) -> bool:
    if f.type == "file":
        return True
    try:
        loc = _locator_for(page, _selector_for(f, value)).first
        if not loc.count():
            return False
        if f.type in ("radio", "checkbox"):
            return bool(loc.is_checked())
        got = loc.input_value(timeout=1500)
        return norm_equals(got, value) or (f.type == "select" and bool(got))
    except Exception:
        return f.type == "custom_select"


# Tags every visible form control with data-afm and returns a description.
# Radios/checkboxes sharing a name are collapsed into one logical field with options.
EXTRACT_JS = r"""
() => {
  const vis = el => {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return ((r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none')
      || el.type === 'file') && !el.disabled;
  };
  const txt = el => (el && (el.innerText || el.textContent) ? (el.innerText || el.textContent) : '').replace(/\s+/g, ' ').trim();
  const labelOf = el => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return txt(l); }
    const ll = el.getAttribute('aria-labelledby');
    if (ll) { const t = ll.split(' ').map(i => txt(document.getElementById(i))).join(' ').trim(); if (t) return t; }
    const wrap = el.closest('label'); if (wrap) return txt(wrap);
    const fs = el.closest('fieldset'); if (fs && fs.querySelector('legend')) return txt(fs.querySelector('legend'));
    let p = el.parentElement;
    for (let i = 0; i < 4 && p; i++, p = p.parentElement) {
      const l = p.querySelector('label, legend, [class*="label"]'); if (l && txt(l)) return txt(l);
    }
    return el.placeholder || el.name || '';
  };
  const out = []; const groups = {}; let n = 0;
  document.querySelectorAll('input, textarea, select').forEach(el => {
    const type = el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea' : (el.type || 'text');
    if (['hidden', 'submit', 'button', 'image', 'reset', 'search'].includes(type)) return;
    if (!vis(el)) return;
    if (type === 'radio' || type === 'checkbox') {
      const g = type + ':' + (el.name || labelOf(el));
      const optLabel = txt(el.closest('label')) || (el.id && txt(document.querySelector(`label[for="${CSS.escape(el.id)}"]`))) || el.value;
      if (!groups[g]) {
        const key = 'f' + (n++);
        groups[g] = {
          key,
          label: (el.closest('fieldset') && el.closest('fieldset').querySelector('legend'))
            ? txt(el.closest('fieldset').querySelector('legend')) : labelOf(el),
          type, required: el.required || el.getAttribute('aria-required') === 'true',
          options: [], name: el.name || '', element_id: el.id || '', placeholder: '',
          current: '', checked: false, frame_index: 0
        };
        out.push(groups[g]);
      }
      el.setAttribute('data-afm', groups[g].key + '|' + optLabel);
      if (!groups[g].options.includes(optLabel)) groups[g].options.push(optLabel);
      if (el.checked) { groups[g].checked = true; groups[g].current = groups[g].current ? groups[g].current + '|' + optLabel : optLabel; }
      return;
    }
    const key = 'f' + (n++);
    el.setAttribute('data-afm', key);
    const f = {
      key, label: labelOf(el), type,
      required: el.required || el.getAttribute('aria-required') === 'true',
      options: [], name: el.name || '', element_id: el.id || '',
      placeholder: el.placeholder || '', current: '', checked: false, frame_index: 0
    };
    if (type === 'select') {
      f.options = [...el.options].map(o => o.text.trim()).filter(t => t && !/^select/i.test(t));
      if (el.selectedIndex >= 0 && el.options[el.selectedIndex]) {
        const st = (el.options[el.selectedIndex].text || '').trim();
        f.current = /^select/i.test(st) ? '' : st;
      }
    } else if (type === 'file') {
      f.current = '';
    } else {
      f.current = el.value || '';
    }
    out.push(f);
  });
  // Custom listbox/combobox controls (ARIA widgets used by many ATS forms).
  document.querySelectorAll('[role="combobox"], button[aria-haspopup="listbox"]').forEach(el => {
    if (!vis(el)) return;
    if (el.closest('label')) return;
    const key = 'f' + (n++);
    el.setAttribute('data-afm', key);
    const owns = el.getAttribute('aria-controls') || el.getAttribute('aria-owns') || '';
    let opts = [];
    try {
      const box = owns ? document.getElementById(owns) : document.querySelector('[role="listbox"]');
      opts = box ? [...box.querySelectorAll('[role="option"]')].map(o => txt(o)).filter(Boolean) : [];
    } catch (_) {}
    out.push({
      key, label: labelOf(el) || txt(el), type: 'custom_select',
      required: el.getAttribute('aria-required') === 'true',
      options: opts, name: el.getAttribute('name') || '', element_id: el.id || '',
      placeholder: '', current: el.getAttribute('aria-valuetext') || '',
      checked: false, frame_index: 0
    });
  });
  return out;
}
"""

SYSTEM = """You fill out a job application form on behalf of a candidate.
For every form field return the value to enter, using ONLY the candidate profile, the tailored
cover letter, and the job info provided.
RULES:
- NEVER invent facts. If the answer is not derivable from the profile, set value to null (a human will answer).
- For select/radio fields, value MUST be exactly one of the listed options. For checkbox groups, a single option label.
- For consent/privacy/terms checkboxes required to apply, choose the affirmative option.
- For EEO/demographic questions use the profile's screening answers; if absent choose a 'decline'-style option.
- For file fields: resume => value 'RESUME'; cover letter file => value 'COVER_LETTER'; anything else => null.
- For a 'cover letter' textarea, use the tailored cover letter text.
- Free-text 'why us' style questions: write 2-4 grounded sentences from the profile, specific to THIS job's
  description, in a natural voice (no 'I am passionate about'); if impossible, null.
- Name fields: use the candidate's preferred name unless the field says 'legal name'.
- Yes/no basics (18+, background check, previously employed here, how did you hear about us) come from
  profile.screening if present; never invent criminal-history, citizenship or licence answers - null instead.
- SALARY: if the job description shows a pay range, answer with its midpoint (convert currency only if the profile
  gives a conversion note); otherwise use profile.compensation.salary_expectation. Never go below
  salary_range_min. Hourly rate = annual / 2080. Asked for a range: expectation +/- 10%.
- Skills questions ("experience with X?"): answer yes only for skills or clearly adjacent work in the profile.
- confidence: 0-1 how sure you are."""


class Answers(BaseModel):
    answers: list[FieldAnswer]


def _page_frames(page: Page) -> list:
    try:
        main = page.main_frame
        return [main] + [f for f in page.frames if f != main]
    except Exception:
        return []


def extract_fields(page: Page) -> list[FormField]:
    """Fresh snapshot of every frame; never reuse handles from a previous step."""
    out: list[FormField] = []
    for idx, frame in enumerate(_page_frames(page)):
        try:
            items = frame.evaluate(EXTRACT_JS) or []
        except Exception:
            continue
        for item in items:
            item["frame_index"] = idx
            try:
                out.append(FormField(**item))
            except Exception:
                continue
    return out


def plan_answers(fields: list[FormField], job: Job, profile: Profile, tailored: Tailored) -> list[FieldAnswer]:
    user = json.dumps(
        {
            "job": {"title": job.title, "company": job.company, "location": job.location, "description": job.description[:3000]},
            "candidate": profile.model_dump(exclude={"sources"}),
            "cover_letter": tailored.cover_letter,
            "fields": [f.model_dump(exclude={"frame_index", "current", "checked"}) for f in fields],
        }
    )
    return ask_json(SYSTEM, user, Answers).answers


def _selector_for(f: FormField, value: str) -> str:
    if f.type in ("radio", "checkbox"):
        return f'[data-afm="{f.key}|{value}"]'
    return f'[data-afm="{f.key}"]'


def _locator_for(page: Page, selector: str):
    """Resolve a tagged control in any frame, surviving iframe re-renders."""
    loc = page.locator(selector)
    try:
        if loc.count():
            return loc
    except Exception:
        pass
    for frame in _page_frames(page)[1:]:
        try:
            fl = frame.locator(selector)
            if fl.count():
                return fl
        except Exception:
            continue
    return loc


def _fill(page: Page, f: FormField, value: str, resume: Path, cover_pdf: Path | None) -> None:
    selector = _selector_for(f, value)
    loc_all = _locator_for(page, selector)
    if f.type == "file":
        if value == "RESUME":
            loc_all.first.set_input_files(str(resume))
        elif value == "COVER_LETTER" and cover_pdf:
            loc_all.first.set_input_files(str(cover_pdf))
    elif f.type == "select":
        el = loc_all.first
        try:
            el.select_option(label=value)
        except Exception:
            opts = el.evaluate("e => [...e.options].map(o => o.text.trim())")
            m = next((o for o in opts if value.lower() in o.lower() or o.lower() in value.lower()), None)
            if m:
                el.select_option(label=m)
        try:
            el.dispatch_event("change")
        except Exception:
            pass
    elif f.type == "custom_select":
        el = loc_all.first
        try:
            el.click(timeout=4000)
            page.wait_for_timeout(350)
            option = page.get_by_role("option", name=re.compile(re.escape(value), re.I))
            if not option.count():
                option = page.locator(f'[role="option"]:has-text("{value}")')
            if option.count():
                option.first.click(timeout=4000)
                page.wait_for_timeout(250)
                return
            raise RuntimeError(f"option {value!r} not found in custom dropdown")
        except Exception:
            el.fill(value)
            page.wait_for_timeout(300)
            page.keyboard.press("Enter")
    elif f.type in ("radio", "checkbox"):
        el = loc_all
        if not el.count():
            group = _locator_for(page, f'[data-afm^="{f.key}"]')
            for i in range(group.count()):
                cand = group.nth(i)
                try:
                    if value.lower() in (cand.get_attribute("data-afm") or "").lower():
                        el = cand
                        break
                except Exception:
                    continue
        if el.count():
            el.first.check(force=True)
            try:
                el.first.dispatch_event("change")
            except Exception:
                pass
    else:
        el = loc_all.first
        el.fill(value, timeout=5000)
        try:
            el.dispatch_event("change")
            el.blur()
        except Exception:
            pass


def _is_required(f: FormField) -> bool:
    return f.required or "*" in f.label or "required" in f.label.lower()


VISIBLE_ERRORS_JS = r"""
() => [...document.querySelectorAll('[aria-invalid="true"], [role="alert"], .error, .errors, .field-error, [class*="error-message"], [class*="invalid"], [data-test-form-element-error]')]
  .filter(e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && ((e.innerText || '').trim() || e.getAttribute('aria-invalid') === 'true');
  })
  .map(e => ((e.innerText || e.getAttribute('aria-label') || '').trim()).slice(0, 160))
  .filter(Boolean)
"""


def page_body_text(page: Page, limit: int = 8000) -> str:
    try:
        return page.evaluate("() => document.body ? document.body.innerText.slice(0, %d) : ''" % int(limit)) or ""
    except Exception:
        return ""


def visible_errors(page: Page) -> list[str]:
    try:
        return [str(x) for x in (page.evaluate(VISIBLE_ERRORS_JS) or []) if str(x).strip()]
    except Exception:
        return []


def validate_form(page: Page) -> tuple[list[str], list[str]]:
    """Return (visible validation messages, labels of empty required fields)."""
    errors = visible_errors(page)
    empty: list[str] = []
    for f in extract_fields(page):
        if not _is_required(f) or f.type == "file":
            continue
        if f.type in ("radio", "checkbox"):
            if not f.checked:
                empty.append(f.label or f.key)
        elif not (f.current or "").strip():
            empty.append(f.label or f.key)
    return errors, empty


def _hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8", "replace")).hexdigest()[:16]


def step_signature(page: Page) -> str:
    """Identity of the current wizard step (URL + heading + field labels).

    Values are excluded so typing into a field is not mistaken for a new step.
    """
    try:
        url = re.sub(r"[?#].*$", "", page.url or "")
    except Exception:
        url = ""
    try:
        heading = page.evaluate(
            """() => {
              const sels = ['.jobs-easy-apply-modal h3', '[data-test-modal] h2', '[role="dialog"] h2',
                '[role="dialog"] h3', 'form h2', 'form h3', 'h1'];
              for (const s of sels) { const e = document.querySelector(s); if (e && e.innerText.trim()) return e.innerText.trim(); }
              return '';
            }"""
        ) or ""
    except Exception:
        heading = ""
    fields = tuple((f.type, f.label, tuple(f.options[:6])) for f in extract_fields(page))
    return _hash(json.dumps([url, heading, fields], ensure_ascii=False))


def page_signature(page: Page) -> str:
    """Full observation used for loop detection (step + current values)."""
    try:
        url = re.sub(r"[?#].*$", "", page.url or "")
    except Exception:
        url = ""
    body = _hash(page_body_text(page, 2500))
    fields = tuple((f.type, f.label, f.current, f.checked) for f in extract_fields(page))
    return _hash(json.dumps([url, body, fields], ensure_ascii=False))


def wait_for_page_ready(page: Page, *, timeout_ms: int = 15000) -> None:
    """Wait for navigation/DOM readiness with a bounded timeout; never an unbounded sleep."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=min(4000, timeout_ms))
    except Exception:
        pass


def wait_for_change(page: Page, before: str, *, timeout_ms: int = 8000, machine=None) -> bool:
    """Poll for a real step transition after a click."""
    end = time.time() + timeout_ms / 1000.0
    while time.time() < end:
        if machine is not None:
            machine.check_cancel()
        try:
            if step_signature(page) != before:
                return True
        except Exception:
            return True  # navigation in progress counts as a change
        try:
            page.wait_for_timeout(250)
        except Exception:
            return False
    return False


def detect_blocker(page: Page) -> tuple[str, str] | None:
    """Classify a page-level blocker that requires a human or a different route."""
    url = ""
    try:
        url = page.url or ""
    except Exception:
        pass
    if _linkedin_needs_auth(page):
        return "auth", "LinkedIn is asking you to sign in"
    if url and (why := manual_reason(url)):
        return "manual", why
    text = page_body_text(page, 4000)
    if why := closed_reason(text):
        return "closed", why
    try:
        challenge = detect_captcha(page)
    except Exception:
        challenge = None
    if challenge:
        return "captcha", f"{challenge.kind} captcha requires a human"
    low = (text or "").lower()
    if any(x in low for x in ("verify you are human", "security check", "two-factor", "2fa", "enter the code")):
        return "mfa", "additional verification / 2FA is required"
    if "access denied" in low or "you don't have permission" in low:
        return "blocked", "the site denied access"
    return None


def verify_submission(page: Page, url_before: str, timeout_s: int = 15) -> tuple[str, str]:
    """Poll after clicking Submit. Never assumes success.

    Returns ('applied'|'errors'|'login'|'unverified', note).  Confirmation needs
    an explicit acknowledgement in the page text; a URL change alone is not
    evidence (careers sites redirect to generic /thank-you pages).
    """
    status = "unverified"
    errors: list[str] = []
    deadline = time.time() + max(3, timeout_s)
    while time.time() < deadline:
        try:
            page.wait_for_timeout(600)
        except Exception:
            return "unverified", "browser closed before confirmation could be verified"
        try:
            text = page_body_text(page, 10000)
            errors = visible_errors(page)
            url_after = page.url
        except Exception:
            continue  # navigation in progress
        status = classify_submission(text, url_before, url_after, len(errors))
        if status == "applied":
            return "applied", "confirmation detected"
        if status == "login":
            return "login", "the site redirected to a sign-in page after submit"
        if status == "errors" and errors:
            return "errors", "form validation errors after submit: " + "; ".join(errors)[:220]
        # An explicit confirmation selector is also evidence.
        try:
            confirm = page.locator(
                ".jobs-easy-apply-post-apply, [data-test-modal-id*='post-apply'], "
                "[data-test='application-submitted'], .application-confirmation"
            )
            if confirm.count() and confirm.first.is_visible():
                return "applied", "confirmation dialog detected"
        except Exception:
            pass
    if errors:
        return "errors", "form validation errors after submit: " + "; ".join(errors)[:220]
    return (
        "unverified",
        "Submit was clicked but no confirmation page/message was detected - check the browser and your email before retrying",
    )


def _owner_tag() -> str:
    return f"pid:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _result_for_state(machine: ApplyStateMachine) -> tuple[str, str]:
    st = machine.state
    if st in (ApplyState.APPLICATION_CONFIRMED, ApplyState.APPLICATION_SUBMITTED, ApplyState.ALREADY_SUBMITTED):
        return "applied", "application confirmed"
    if st is ApplyState.CANCELLED:
        return "cancelled", "cancelled by user"
    if st is ApplyState.AWAITING_USER_REVIEW:
        return "awaiting_review", machine.last_error or "form filled and waiting for review"
    if st is ApplyState.AUTHENTICATION_REQUIRED:
        return "manual", machine.last_error or "sign-in required"
    if st is ApplyState.HUMAN_INTERVENTION_REQUIRED:
        return "manual", machine.last_error or "human intervention required"
    if st is ApplyState.FAILED:
        return "failed", machine.last_error or "application failed"
    return "errors", machine.last_error or "application did not reach a terminal state"


def apply(
    job: Job,
    profile: Profile,
    tailored: Tailored,
    *,
    store=None,
    dry_run: bool = False,
    auto_submit: bool = False,
    ask_terminal: bool = False,
    authorize_submit: bool = False,
    session_owner: str | None = None,
) -> tuple[str, str]:
    """Return (status, note).

    status: ``applied`` (confirmed), ``awaiting_review`` (filled, needs an
    explicit submit), ``filled`` (dry run), ``needs_feedback``, ``manual``
    (auth/CAPTCHA/SSO), ``blocked``, ``closed``, ``cancelled``,
    ``already_submitted``, ``busy``, ``errors`` or ``unverified``.
    """
    resume = (ROOT / profile.resume_path).resolve() if not Path(profile.resume_path).is_absolute() else Path(profile.resume_path)
    if tailored.resume_pdf and Path(tailored.resume_pdf).exists():
        resume = Path(tailored.resume_pdf)  # per-job tailored resume
    if not resume.exists():
        raise SystemExit(f"Resume not found at {resume}")

    ensure_playwright_browsers_path()
    store = store if store is not None else Store()
    owner = session_owner or _owner_tag()

    # Never start a second application for a job that already has a confirmed
    # submission.  This is the last line of defence against double-submits.
    if store.submission_recorded(job.id):
        print(f"[applier] {job.id} already has a confirmed submission — refusing to re-apply")
        return "already_submitted", "a confirmed submission is already recorded for this job"

    lock_ttl = _apply_timeout_sec() + _review_timeout_sec() + 180
    if not store.acquire_apply_lock(job.id, owner, ttl_sec=lock_ttl):
        row = store.apply_session(job.id) or {}
        return "busy", f"another apply worker is already handling this job (owner={row.get('lock_owner') or 'unknown'})"

    try:
        # A cancellation that arrived before this process started wins over a
        # prepare run.  Prepare explicitly clears a stale flag in the dashboard.
        if store.is_apply_cancelled(job.id):
            # Cancel wins over a submit flag: the user asked us to stop before
            # this process crossed the submit boundary.
            store.clear_apply_cancel(job.id)
            return "cancelled", "cancelled by user"
        store.clear_apply_cancel(job.id)
        started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        explicit = bool(authorize_submit or auto_submit)
        if explicit:
            # The dashboard may already have recorded a named, one-shot
            # authorization.  Do not overwrite its audit identity with "cli".
            if not store.apply_submit_authorized(job.id):
                store.authorize_apply(job.id, by="cli" if authorize_submit else "cli-auto")
        machine = ApplyStateMachine(
            store,
            job.id,
            owner=owner,
            max_steps=_max_apply_steps(),
            # Prepare ignores authorizations from older runs; Submit is explicit.
            submit_authorized_after=None if explicit else started_at,
        )
        if machine.state is ApplyState.CANCELLED:
            return "cancelled", "cancelled by user"
        if machine.state in (ApplyState.APPLICATION_CONFIRMED, ApplyState.APPLICATION_SUBMITTED, ApplyState.ALREADY_SUBMITTED):
            return "applied", "application was already confirmed"
        if machine.state is ApplyState.IDLE:
            machine.start()
        else:
            machine.resume()
        if machine.state in (
            ApplyState.JOB_SELECTED, ApplyState.JOB_DETAILS_LOADED, ApplyState.IDLE,
            ApplyState.RETRY_PENDING, ApplyState.BROWSER_INITIALIZED,
        ):
            machine.transition(ApplyState.PROFILE_READY, result="profile", detail=f"resume={resume.name}")

        try:
            if firecrawl_enabled():
                try:
                    return _apply_via_firecrawl(
                        job, profile, tailored,
                        resume=resume, store=store, dry_run=dry_run,
                        auto_submit=auto_submit, ask_terminal=ask_terminal,
                        machine=machine,
                    )
                except (Cancelled, LoopDetected, BudgetExceeded):
                    raise
                except Exception as e:
                    err = str(e)
                    print(f"[applier] Firecrawl apply failed ({err}) — falling back to local Playwright")
                    try:
                        kill_stale_apply_browsers()
                    except Exception:
                        pass
            return _apply_via_local_playwright(
                job, profile, tailored,
                resume=resume, store=store, dry_run=dry_run,
                auto_submit=auto_submit, ask_terminal=ask_terminal,
                machine=machine,
            )
        except Cancelled as e:
            # Consume the cancellation flag so the next explicit prepare can
            # start cleanly; the job status stays "cancelled" until then.
            store.clear_apply_cancel(job.id)
            print(f"[applier] cancelled: {e}")
            return "cancelled", str(e) or "cancelled by user"
        except LoopDetected as e:
            store.add_event(job.id, "apply_failed", "Apply stopped: browser loop", str(e)[:800])
            print(f"[applier] loop stopped: {e}")
            return "failed", str(e)
        except BudgetExceeded as e:
            store.add_event(job.id, "apply_failed", "Apply stopped: budget exhausted", str(e)[:800])
            print(f"[applier] budget exhausted: {e}")
            return "failed", str(e)
        except ApplyStateError as e:
            store.add_event(job.id, "apply_failed", "Apply state error", str(e)[:800])
            print(f"[applier] state error: {e}")
            return "failed", str(e)
    finally:
        try:
            store.release_apply_lock(job.id, owner)
        except Exception:
            pass


def _apply_via_firecrawl(
    job: Job,
    profile: Profile,
    tailored: Tailored,
    *,
    resume: Path,
    store,
    dry_run: bool,
    auto_submit: bool,
    ask_terminal: bool,
    machine: ApplyStateMachine,
) -> tuple[str, str]:
    """Crawl the exact job URL with Firecrawl, then LLM-fill fields over CDP."""
    from ..firecrawl_apply import crawl_apply

    ensure_playwright_browsers_path()
    print("[applier] Firecrawl crawl-apply — exact job link + LLM field fill")
    return crawl_apply(
        job, profile, tailored,
        resume=resume, store=store, dry_run=dry_run,
        auto_submit=auto_submit, ask_terminal=ask_terminal,
        write_live=_write_live, machine=machine,
    )


def _profile_locked_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(x in msg for x in (
        "processsingleton", "user data directory is already in use", "profile is already in use",
        "cannot create a second instance", "target page, context or browser has been closed",
    ))


def _apply_via_local_playwright(
    job: Job,
    profile: Profile,
    tailored: Tailored,
    *,
    resume: Path,
    store,
    dry_run: bool,
    auto_submit: bool,
    ask_terminal: bool,
    machine: ApplyStateMachine,
) -> tuple[str, str]:
    from ..browser_runtime import acquire_browser_lock, release_browser_lock

    headed = _headed()
    slow = _slow_mo_ms() if headed else 0
    user_data = prepare_local_browser(kill_stale=False)
    deadline = time.time() + _apply_timeout_sec()
    browser_lock = acquire_browser_lock(timeout_sec=max(30, _apply_timeout_sec()))
    if browser_lock is None:
        machine.transition(
            ApplyState.HUMAN_INTERVENTION_REQUIRED,
            result="busy",
            detail="another Apply browser session is already running",
        )
        return "busy", "another Apply browser session is already running — finish it or wait, then retry"
    print(
        f"[applier] launching local Chromium headed={headed} slow_mo={slow}ms "
        f"profile={user_data} timeout={_apply_timeout_sec()}s"
    )

    try:
        with sync_playwright() as pw:
            ctx = None
            try:
                ctx = pw.chromium.launch_persistent_context(
                    str(user_data),
                    headless=not headed,
                    slow_mo=slow,
                    viewport={"width": 1280, "height": 900},
                    args=["--start-maximized"] if headed else [],
                )
            except Exception as e:
                if not _profile_locked_error(e):
                    raise
                print(f"[applier] browser profile lock detected ({e}) — clearing a stale lock once")
                kill_stale_apply_browsers()
                ctx = pw.chromium.launch_persistent_context(
                    str(user_data),
                    headless=not headed,
                    slow_mo=slow,
                    viewport={"width": 1280, "height": 900},
                    args=["--start-maximized"] if headed else [],
                )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            machine.transition(ApplyState.BROWSER_INITIALIZED, result="browser", detail="persistent Chromium started")
            try:
                _write_live(job, page, "opening", "Loading application page…", engine="playwright")
                return _apply_in_browser(
                    page, job, profile, tailored,
                    resume=resume, store=store, dry_run=dry_run,
                    auto_submit=auto_submit, ask_terminal=ask_terminal,
                    headed=headed, deadline=deadline, machine=machine,
                )
            except Cancelled:
                raise
            except LoopDetected:
                raise
            except BudgetExceeded:
                raise
            except TimeoutError as e:
                msg = str(e)
                print(f"[applier] {msg}")
                try:
                    _write_live(job, None, "timeout", msg[:180], engine="playwright")
                except Exception:
                    pass
                if machine.state not in (ApplyState.FAILED, ApplyState.CANCELLED):
                    try:
                        machine.transition(ApplyState.FAILED, result="timeout", detail=msg)
                    except Exception:
                        pass
                return "errors", msg
            except Exception as e:
                msg = str(e)
                if "has been closed" in msg.lower() or "target page" in msg.lower():
                    msg = "browser closed during apply (not submitted) — click Prepare again for a fresh browser"
                print(f"[applier] interrupted: {msg}")
                try:
                    _write_live(job, page if _page_alive(page) else None, "errors", msg[:180], engine="playwright")
                except Exception:
                    pass
                if machine.state not in (ApplyState.FAILED, ApplyState.CANCELLED):
                    try:
                        machine.transition(ApplyState.FAILED, result="error", detail=msg)
                    except Exception:
                        pass
                return "errors", f"apply interrupted (not submitted): {msg}"
            finally:
                try:
                    _write_live(job, None, "done", "Browser closed", engine="playwright")
                except Exception:
                    pass
                try:
                    ctx.close()
                except Exception:
                    pass
                try:
                    from ..browser_runtime import clear_profile_locks

                    clear_profile_locks()
                except Exception:
                    pass
    finally:
        release_browser_lock(browser_lock)


def _handle_submit(
    page: Page,
    job: Job,
    *,
    resume: Path,
    store,
    machine: ApplyStateMachine,
    dry_run: bool,
    auto_submit: bool,
    headed: bool,
    deadline: float | None,
    url_before: str,
    dry_run_note: str = "dry run - nothing submitted",
) -> tuple[str, str]:
    """Review -> explicit authorization -> one idempotent submit -> verify."""
    if dry_run:
        machine.transition(ApplyState.AWAITING_USER_REVIEW, result="dry_run", detail="dry run; not submitted")
        _write_live(job, page, "filled", "Dry run — form filled, nothing submitted")
        _watch_filled_form(page, job, _watch_seconds(), deadline)
        return "filled", dry_run_note

    if machine.submission_already_recorded():
        machine.transition(ApplyState.ALREADY_SUBMITTED, result="already", detail="confirmed submission already recorded")
        return "applied", "application was already confirmed; not submitting again"

    if not machine.authorized_for_submission():
        machine.transition(
            ApplyState.AWAITING_USER_REVIEW,
            result="review",
            detail="form filled; waiting for explicit submit authorization",
        )
        _write_live(
            job, page, "awaiting_confirm",
            "Form filled — review it, then press Submit application in the dashboard (or Submit in the browser).",
        )
        print("[applier] waiting for explicit submit authorization (dashboard Submit button)")
        approved = _wait_for_authorization(
            machine, store, timeout_sec=_review_timeout_sec(), deadline=deadline
        )
        if machine.submission_already_recorded():
            machine.transition(ApplyState.ALREADY_SUBMITTED, result="already", detail="submission appeared during review")
            return "applied", "application was confirmed while waiting for review"
        if not approved:
            machine.last_error = "form filled; submit authorization timed out"
            store.clear_apply_authorization(job.id)
            return "awaiting_review", "form filled and waiting for your explicit submit authorization"

    machine.transition(ApplyState.SUBMISSION_IN_PROGRESS, result="submit", detail="explicit authorization received")
    _check_deadline(deadline)

    # Re-upload right before submit in case the site reset the document choice.
    _upload_tailored_resume(page, resume)
    cap_ok, cap_note = _prepare_captcha_for_submit(page, job, deadline)
    if not cap_ok:
        machine.transition(
            ApplyState.HUMAN_INTERVENTION_REQUIRED, result="captcha", detail=cap_note
        )
        _write_live(job, page, "captcha", cap_note)
        _watch_filled_form(page, job, min(30, _captcha_manual_sec()), deadline)
        store.clear_apply_authorization(job.id)
        return "manual", cap_note

    if machine.submission_already_recorded():
        machine.transition(ApplyState.ALREADY_SUBMITTED, result="already", detail="confirmed submission already recorded")
        return "applied", "application was already confirmed; not submitting again"

    # Record the attempt BEFORE clicking.  If the process dies after the click,
    # the next run will not submit again; it will ask the user to verify.
    if not store.record_submission_attempt(job.id):
        machine.transition(
            ApplyState.HUMAN_INTERVENTION_REQUIRED,
            result="unverified",
            detail="a previous submit attempt was not confirmed; refusing to submit twice",
        )
        store.clear_apply_authorization(job.id)
        return (
            "unverified",
            "A previous submit click was recorded but no confirmation was seen. Check your email / the site before retrying; the agent will not submit twice.",
        )

    _write_live(job, page, "submitting", "Clicking Submit…")
    if not _click_submit_control(page):
        machine.transition(
            ApplyState.HUMAN_INTERVENTION_REQUIRED,
            result="no_submit",
            detail="submit control not clickable; form may still have validation errors",
        )
        _write_live(job, page, "manual", "Submit control not clickable — finish in live view")
        store.clear_apply_authorization(job.id)
        return "manual", "Could not click a real Submit control — check validation errors in the live browser"

    status, note = verify_submission(
        page, url_before, timeout_s=min(20, max(6, int(_deadline_left(deadline) or 20)))
    )
    _write_live(job, page, status, note)

    if status == "applied":
        machine.confirm_submission(note, strong=True)
        return "applied", note
    if status == "errors":
        # Validation stopped the submit; no application was sent.  Clear the
        # idempotency marker so the human can fix and submit once.
        if hasattr(store, "clear_submission_attempt"):
            store.clear_submission_attempt(job.id)
        store.clear_apply_authorization(job.id)
        machine.transition(ApplyState.FORM_VALIDATING, result="errors", detail=note)
        return "errors", note
    if status == "login":
        store.clear_apply_authorization(job.id)
        machine.transition(ApplyState.AUTHENTICATION_REQUIRED, result="login", detail=note)
        return "manual", note
    # Unverified: do NOT retry automatically.  The click may have succeeded.
    store.clear_apply_authorization(job.id)
    machine.transition(ApplyState.HUMAN_INTERVENTION_REQUIRED, result="unverified", detail=note)
    return "unverified", note


def _apply_in_browser(
    page: Page,
    job: Job,
    profile: Profile,
    tailored: Tailored,
    *,
    resume: Path,
    store,
    dry_run: bool,
    auto_submit: bool,
    ask_terminal: bool,
    headed: bool,
    deadline: float | None = None,
    skip_initial_goto: bool = False,
    machine: ApplyStateMachine | None = None,
) -> tuple[str, str]:
    machine = machine or ApplyStateMachine(store, job.id, owner=_owner_tag(), max_steps=_max_apply_steps())
    answer_cache: dict[str, str] = {}
    target = job.target_url()
    if not target:
        machine.transition(ApplyState.FAILED, result="no_target", detail="job has no apply URL")
        return "errors", "job has no apply URL"

    if machine.state in (
        ApplyState.APPLICATION_CONFIRMED, ApplyState.APPLICATION_SUBMITTED, ApplyState.ALREADY_SUBMITTED
    ):
        return "applied", "application was already confirmed; not submitting again"

    machine.check_cancel()
    if machine.submission_already_recorded():
        machine.transition(
            ApplyState.ALREADY_SUBMITTED, result="already",
            detail="confirmed submission already recorded", force=True,
        )
        return "applied", "application was already confirmed; not submitting again"

    # ---------------------------------------------------------- navigate
    if skip_initial_goto:
        machine.transition(ApplyState.APPLICATION_PAGE_READY, result="resumed", detail="already on application page")
        print("[applier] already on job / Easy Apply modal — skipping initial goto")
    else:
        machine.transition(ApplyState.NAVIGATING, result="goto", detail=target[:300])
        _write_live(job, page, "opening", "Loading application page…")
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                page.goto(target, wait_until="domcontentloaded", timeout=60000)
                wait_for_page_ready(page, timeout_ms=15000)
                last_error = None
                break
            except Exception as e:
                last_error = e
                print(f"[applier] navigation attempt {attempt + 1}/3 failed: {e}")
                if attempt < 2:
                    machine.retry(f"navigation failed: {e}")
                    time.sleep(0.5)
        if last_error is not None:
            machine.transition(ApplyState.FAILED, result="navigation", detail=str(last_error)[:500])
            return "errors", f"could not load the application page: {last_error}"
        machine.transition(ApplyState.APPLICATION_PAGE_READY, result="loaded", detail=page.url[:300])
    try:
        page.bring_to_front()
    except Exception:
        pass
    _write_live(job, page, "loaded", "Page loaded")

    # ---------------------------------------------------------- blockers
    blocker = detect_blocker(page)
    linkedin = _is_linkedin(page.url) or _is_linkedin(target)
    if blocker:
        kind, why = blocker
        if kind == "auth" or (linkedin and _linkedin_needs_auth(page)):
            machine.transition(ApplyState.AUTHENTICATION_REQUIRED, result="auth", detail=why)
            _write_live(job, page, "linkedin_login", why)
            if not _wait_linkedin_login(page, job, force=True, deadline=deadline):
                machine.last_error = "sign-in timed out"
                return "manual", "Sign-in timed out — sign in once in the browser window, then click Prepare again"
            machine.transition(ApplyState.APPLICATION_PAGE_READY, result="auth_ok", detail="signed in")
        elif kind == "closed":
            machine.transition(ApplyState.FAILED, result="closed", detail=why)
            _write_live(job, page, "closed", why)
            return "closed", why
        elif kind == "manual":
            machine.transition(ApplyState.HUMAN_INTERVENTION_REQUIRED, result="manual", detail=why)
            _write_live(job, page, "manual", why)
            return "manual", why
        else:
            machine.transition(ApplyState.HUMAN_INTERVENTION_REQUIRED, result=kind, detail=why)
            _write_live(job, page, "manual", why)
            _watch_filled_form(page, job, min(60, _captcha_manual_sec()), deadline)
            return "manual", why

    # LinkedIn may show the sign-in modal only after clicking Apply.
    easy = False
    if linkedin:
        if _linkedin_needs_auth(page):
            machine.transition(ApplyState.AUTHENTICATION_REQUIRED, result="auth", detail="LinkedIn sign-in required")
            if not _wait_linkedin_login(page, job, force=True, deadline=deadline):
                machine.last_error = "sign-in timed out"
                return "manual", "Sign into LinkedIn in the browser window, then click Prepare again"
            machine.transition(ApplyState.APPLICATION_PAGE_READY, result="auth_ok", detail="signed in")
        if _easy_apply_modal_open(page):
            easy = True
            print("[applier] LinkedIn Easy Apply modal already open")
        else:
            _write_live(job, page, "easy_apply", "Looking for Easy Apply…")
            easy = _click_easy_apply(page)
            wait_for_page_ready(page, timeout_ms=6000)
        if easy:
            print("[applier] LinkedIn Easy Apply opened")
            if _linkedin_needs_auth(page):
                machine.transition(ApplyState.AUTHENTICATION_REQUIRED, result="auth", detail="sign-in modal after Apply")
                if not _wait_linkedin_login(page, job, force=True, deadline=deadline):
                    machine.last_error = "sign-in timed out"
                    return "manual", "Sign into LinkedIn, then click Prepare again"
                # Re-open the job page without losing the sign-in; never trust
                # a stale modal after an auth redirect.
                machine.transition(ApplyState.NAVIGATING, result="reload", detail=target[:300])
                page.goto(target, wait_until="domcontentloaded", timeout=60000)
                wait_for_page_ready(page, timeout_ms=10000)
                easy = _click_easy_apply(page)
        else:
            print("[applier] No Easy Apply — this posting uses company-site Apply")
            _write_live(job, page, "external_apply", "Opening company Apply page…")
            before_pages = list(page.context.pages)
            if _click_external_apply(page):
                page = _newest_page(page.context, before_pages)
                wait_for_page_ready(page, timeout_ms=15000)
                if _linkedin_needs_auth(page):
                    machine.transition(ApplyState.AUTHENTICATION_REQUIRED, result="auth", detail="LinkedIn sign-in required")
                    if not _wait_linkedin_login(page, job, force=True, deadline=deadline):
                        machine.last_error = "sign-in timed out"
                        return "manual", "Sign into LinkedIn, then click Prepare again"
            else:
                machine.transition(
                    ApplyState.HUMAN_INTERVENTION_REQUIRED,
                    result="no_apply",
                    detail="no Easy Apply or external Apply control found",
                )
                _watch_filled_form(page, job, min(60, _linkedin_login_sec()), deadline)
                return "manual", "No Easy Apply / Apply control found — finish in the Chromium window or open the company site"

    # Generic ATS: click Apply to reveal the form (non-LinkedIn).
    if not linkedin and not easy and not extract_fields(page):
        for name in ("Apply for this job", "Apply now", "Apply"):
            btn = page.get_by_role("link", name=name).or_(page.get_by_role("button", name=name))
            if btn.count():
                try:
                    before_pages = list(page.context.pages)
                    btn.first.click(timeout=5000)
                    page = _newest_page(page.context, before_pages)
                    wait_for_page_ready(page, timeout_ms=10000)
                except Exception:
                    pass
                break

    # ---------------------------------------------------------- form loop
    fields = extract_fields(page)
    if not fields:
        machine.transition(
            ApplyState.HUMAN_INTERVENTION_REQUIRED,
            result="no_form",
            detail="no form detected on the page",
        )
        _write_live(job, page, "manual", "no form detected — finish in Chromium or retry")
        _watch_filled_form(page, job, min(45, _watch_seconds() or 45), deadline)
        return "manual", "no form detected — use the Chromium window (LinkedIn Easy Apply may need a manual sign-in)"

    machine.transition(ApplyState.FORM_DETECTED, result="form", detail=f"{len(fields)} fields")
    machine.reset_observation()
    last_upload_sig = ""
    url_before = page.url
    max_steps = min(12, max(1, machine.remaining_steps - 5))

    for step in range(max_steps):
        machine.check_cancel()
        machine.observe(page_signature(page))
        machine.transition(ApplyState.FORM_FILLING, result="fill", detail=f"form step {step + 1}")
        _write_live(job, page, "filling", f"Form step {step + 1}")

        # Upload once per distinct step.  Re-uploading on every loop iteration
        # is slow and can reset the site's own resume selection.
        step_sig = step_signature(page)
        if (easy or _easy_apply_modal_open(page)) and step_sig != last_upload_sig:
            _upload_tailored_resume(page, resume)
            last_upload_sig = step_sig

        blocked, note = _fill_visible_fields(
            page, job, profile, tailored, resume, store, ask_terminal, answer_cache=answer_cache
        )
        if blocked == "needs_feedback":
            machine.transition(
                ApplyState.HUMAN_INTERVENTION_REQUIRED, result="needs_feedback",
                detail=note or "questions need answers",
            )
            print(f"[applier] {note}")
            _write_live(job, page, "needs_feedback", note or "")
            _watch_filled_form(page, job, min(25, _watch_seconds() or 25), deadline)
            return "needs_feedback", note or "waiting for your answers on the dashboard"
        if blocked == "fill_errors":
            machine.transition(
                ApplyState.HUMAN_INTERVENTION_REQUIRED, result="fill_error",
                detail=note or "could not fill required fields",
            )
            _write_live(job, page, "manual", note or "could not fill required fields")
            _watch_filled_form(page, job, min(30, _watch_seconds() or 30), deadline)
            return "errors", note or "could not fill required fields"

        machine.transition(ApplyState.FORM_VALIDATING, result="validate", detail=f"step {step + 1}")

        # Confirmation can appear after a Next (some wizards submit on the last
        # step without a distinct Submit control).
        body = page_body_text(page, 4000)
        if is_confirmation_text(body):
            machine.confirm_submission("confirmation text seen", strong=True)
            _write_live(job, page, "applied", "Application confirmation detected")
            return "applied", "application confirmation detected"

        kind, label = _find_action(page, click=False)
        if kind == "submit":
            return _handle_submit(
                page, job, resume=resume, store=store, machine=machine,
                dry_run=dry_run, auto_submit=auto_submit, headed=headed,
                deadline=deadline, url_before=url_before,
            )
        if kind == "next":
            before = step_sig
            print(f"[applier] advancing step ({label!r})")
            clicked_kind, _ = _find_action(page, click=True)
            if clicked_kind != "next":
                machine.retry("next control changed before click")
                continue
            changed = wait_for_change(page, before, timeout_ms=9000, machine=machine)
            if not changed:
                errors, empty = validate_form(page)
                if empty or errors:
                    detail = "; ".join((errors + [f"required: {x}" for x in empty]))[:500]
                    machine.transition(
                        ApplyState.HUMAN_INTERVENTION_REQUIRED,
                        result="validation", detail=detail,
                    )
                    _write_live(job, page, "manual", f"Form needs you: {detail}")
                    _watch_filled_form(page, job, min(45, _watch_seconds() or 45), deadline)
                    return "manual", f"form needs your input: {detail}"
                # Same step after a click. Retry a bounded number of times,
                # then stop rather than clicking forever.
                machine.retry("Next did not change the form")
                continue
            machine.transition(ApplyState.FORM_DETECTED, result="next", detail=f"advanced from step {step + 1}")
            machine.reset_observation()
            continue

        # No wizard control. Treat as a single-page form and let the submit
        # handler decide; never guess that a "Next" is a submit.
        break

    # Single-page form or wizard ended without an explicit control.
    machine.transition(ApplyState.FORM_VALIDATING, result="final", detail="no further wizard control")
    errors, empty = validate_form(page)
    if empty or errors:
        detail = "; ".join((errors + [f"required: {x}" for x in empty]))[:500]
        machine.transition(ApplyState.HUMAN_INTERVENTION_REQUIRED, result="validation", detail=detail)
        _write_live(job, page, "manual", f"Form needs you: {detail}")
        _watch_filled_form(page, job, min(45, _watch_seconds() or 45), deadline)
        return "manual", f"form needs your input: {detail}"

    return _handle_submit(
        page, job, resume=resume, store=store, machine=machine,
        dry_run=dry_run, auto_submit=auto_submit, headed=headed,
        deadline=deadline, url_before=url_before,
    )


def _newest_page(context, before: list):
    """Return the newest page opened by a click, or the original page."""
    try:
        pages = context.pages
        if len(pages) > len(before):
            new = pages[-1]
            try:
                new.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            return new
    except Exception:
        pass
    return context.pages[0] if context.pages else before[0]
