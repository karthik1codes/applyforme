"""Firecrawl cloud browser Apply.

How this works, and why it is shaped this way
--------------------------------------------
Firecrawl exposes two browser entry points:

* **Scrape -> Interact** — ``POST /v2/scrape`` returns a ``scrapeId`` and
  ``POST /v2/scrape/{scrapeId}/interact`` runs actions in the browser bound to
  that scrape.
* **Browser Sandbox** — ``POST /v2/interact`` starts a standalone session
  that needs no prior scrape and hands back a raw CDP websocket url.

Both return the same three urls:

* ``cdpUrl``                — raw Chrome DevTools Protocol websocket
* ``liveViewUrl``           — watch the session
* ``interactiveLiveViewUrl``— click/type in the session (this is what lets the
  user sign in to LinkedIn by hand)

The decisive constraint is the **profile write lock**: a named persistent
profile has exactly one writer (``profile.saveChanges = true``).  While our
session is alive, any other session on that profile is rejected with::

    HTTP 409  Browser operation conflicts with the current session or profile state.

The old implementation used scrape + interact and therefore had three
problems that produced the observed "run again and it fails again" loop:

1. The scrape-bound session id and the browser session id are different
   objects, and the old code could leave the browser session alive.  The next
   run then hit HTTP 409 on its first ``interact`` call and died.
2. It used ``interact(prompt=...)``, i.e. an AI agent driving the browser
   (7 credits/minute, nondeterministic), to do things our own Playwright code
   already does deterministically and for 2 credits/minute.
3. It read ``cdp_url`` off an ``interact`` response, so a session that only
   existed because of a scrape had to be kept alive just to get a CDP url.

This implementation instead:

* opens **one** standalone session it owns (:func:`open_apply_session`),
  records the id in the shared store, and always releases it in ``finally``;
* drives the whole application flow with the same deterministic local
  Playwright code used for the local browser, over the CDP websocket — no AI
  browser agent in the loop;
* surfaces the interactive live view so the user can sign in to LinkedIn
  themselves while the session waits;
* reclaims a stale session left by a crashed run, so one crash cannot wedge
  the profile for every later run.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from playwright.sync_api import sync_playwright

from .browser_runtime import ensure_playwright_browsers_path
from .firecrawl_browser import (
    firecrawl_api_key,
    open_apply_session,
    profile_name,
)
from .models import Job, Profile, Tailored

LiveWriter = Callable[..., None]


def _profile_name() -> str:
    return profile_name()


def job_target(job: Job) -> str:
    target = job.target_url()
    if not target:
        raise RuntimeError("Job has no apply_url or url — cannot apply")
    return target


def _urls_match(expected: str, actual: str) -> bool:
    """True when two URLs point at the same posting.

    Used by diagnostics to confirm the browser really landed on the requested
    job rather than a similar-looking page.
    """
    if not expected or not actual:
        return False
    from urllib.parse import urlparse

    ep, ap_ = urlparse(expected), urlparse(actual)
    if (ep.netloc or "").lower() != (ap_.netloc or "").lower():
        return False
    e = (ep.path or "").rstrip("/").lower()
    a = (ap_.path or "").rstrip("/").lower()
    if e and (e == a or a.startswith(e + "/") or e.startswith(a + "/")):
        return True
    # LinkedIn job id token — only when both URLs contain the same id.
    eids = [p for p in e.split("/") if p.isdigit() and len(p) >= 6]
    aids = [p for p in a.split("/") if p.isdigit() and len(p) >= 6]
    return bool(set(eids) & set(aids))


def crawl_apply(
    job: Job,
    profile: Profile,
    tailored: Tailored,
    *,
    resume: Path,
    store=None,
    dry_run: bool = False,
    auto_submit: bool = False,
    ask_terminal: bool = False,
    write_live: LiveWriter | None = None,
    machine=None,
) -> tuple[str, str]:
    """Apply with a Firecrawl cloud browser driven over CDP."""
    from .agents import applier as ap

    ensure_playwright_browsers_path()
    if not firecrawl_api_key():
        raise RuntimeError("FIRECRAWL_API_KEY missing")

    target = job_target(job)
    print(f"[firecrawl] opening cloud browser session (profile={_profile_name()!r})\n  {target}")

    session = open_apply_session(store=store, job_id=job.id)
    live = session.live_view_url
    interactive = session.interactive_live_view_url or session.live_view_url

    def _live(phase: str, note: str) -> None:
        if write_live:
            write_live(
                job, None, phase, note,
                live_view_url=live,
                interactive_live_view_url=interactive,
                engine="firecrawl",
            )

    try:
        _live("opening", f"Firecrawl browser → {target}")

        deadline = time.time() + ap._apply_timeout_sec()
        print(f"[firecrawl] apply timeout={ap._apply_timeout_sec()}s")

        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(session.cdp_url)
            try:
                ctx = browser.contexts[0] if browser.contexts else browser.new_context(
                    viewport={"width": 1280, "height": 900}
                )
                page = ctx.pages[0] if ctx.pages else ctx.new_page()

                # A LinkedIn sign-in wall is expected on a fresh profile.  The
                # user signs in by hand through the interactive live view;
                # we never type their password and never inject cookies.
                if ap._is_linkedin(target) and ap._linkedin_needs_auth(page):
                    note = (
                        "Sign in to LinkedIn in the live view below (including any 2FA) — "
                        "the agent will not ask for your password."
                    )
                    print(f"[firecrawl] {note}")
                    _live("linkedin_login", note)
                    try:
                        signed_in = ap._wait_linkedin_login(
                            page, job, force=True, deadline=deadline, headed=True
                        )
                    except TimeoutError:
                        signed_in = False
                    if not signed_in:
                        msg = ap._linkedin_auth_note(headed=True)
                        if machine is not None:
                            machine.last_error = msg
                        return "manual", msg
                    if write_live:
                        write_live(
                            job, page, "linkedin_ok", "Signed in to LinkedIn — continuing",
                            live_view_url=live,
                            interactive_live_view_url=interactive,
                            engine="firecrawl",
                        )

                # The local flow knows how to reach the apply form, fill it,
                # validate it and wait for review.  Reuse it verbatim so both
                # engines behave identically.
                return ap._apply_in_browser(
                    page,
                    job,
                    profile,
                    tailored,
                    resume=resume,
                    store=store,
                    dry_run=dry_run,
                    auto_submit=auto_submit,
                    ask_terminal=ask_terminal,
                    headed=True,
                    deadline=deadline,
                    machine=machine,
                )
            except TimeoutError as e:
                msg = str(e)
                print(f"[firecrawl] {msg}")
                _live("timeout", msg[:180])
                return "errors", msg
            finally:
                # Disconnect our CDP client only; the session owner releases
                # the remote browser below.
                try:
                    browser.close()
                except Exception:
                    pass
    finally:
        session.close()
        if store is not None:
            try:
                store.forget_firecrawl_sessions([session.id])
            except Exception:
                pass
        if write_live:
            try:
                write_live(
                    job, None, "done", "Firecrawl apply session closed",
                    live_view_url="", interactive_live_view_url="",
                    engine="firecrawl",
                )
            except Exception:
                pass
        print("[firecrawl] session released")
