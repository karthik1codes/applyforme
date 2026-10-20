"""Firecrawl crawl-first Apply: land on the exact job URL, open Apply, LLM-fill fields.

Flow:
  1) scrape(exact job_url) uncached + persistent profile
  2) interact → force that URL + click Easy Apply / Apply
  3) CDP Playwright → force goto again + existing LLM field fill / submit
  4) interact assist if Playwright cannot see Next/Submit
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import sync_playwright

from .browser_runtime import ensure_playwright_browsers_path
from .firecrawl_browser import firecrawl_api_key
from .models import Job, Profile, Tailored

LiveWriter = Callable[..., None]


def _profile_name() -> str:
    return (os.getenv("FIRECRAWL_BROWSER_PROFILE") or "applyforme").strip() or "applyforme"


def job_target(job: Job) -> str:
    target = (job.apply_url or job.url or "").strip()
    if not target:
        raise RuntimeError("Job has no apply_url or url — cannot crawl")
    return target


def _scrape_id(doc: Any) -> str:
    meta = getattr(doc, "metadata", None) or getattr(doc, "metadata_typed", None)
    sid = getattr(meta, "scrape_id", None) if meta is not None else None
    if not sid and isinstance(meta, dict):
        sid = meta.get("scrape_id") or meta.get("scrapeId")
    if not sid and hasattr(doc, "model_dump"):
        sid = (doc.model_dump().get("metadata") or {}).get("scrape_id")
    return (sid or "").strip()


def _candidate_brief(job: Job, profile: Profile, tailored: Tailored) -> dict:
    p = profile.personal or {}
    return {
        "job_url": job_target(job),
        "job_title": job.title,
        "company": job.company,
        "location": job.location,
        "name": p.get("name") or p.get("full_name") or "",
        "email": p.get("email") or "",
        "phone": p.get("phone") or "",
        "linkedin": p.get("linkedin") or p.get("linkedin_url") or "",
        "city": p.get("city") or p.get("location") or "",
        "skills": (profile.skills or [])[:40],
        "screening": profile.screening or {},
        "compensation": profile.compensation or {},
        "cover_letter": (tailored.cover_letter or "")[:2500],
        "why_company": (tailored.why_this_company or "")[:800],
        "summary": (profile.summary or "")[:800],
    }


def _close_prior_sessions(app: Any) -> None:
    try:
        listed = app.list_browsers(status="active")
        for s in getattr(listed, "sessions", None) or []:
            sid = getattr(s, "id", None)
            if sid:
                try:
                    app.delete_browser(sid)
                    print(f"[firecrawl] closed prior browser session {sid}")
                except Exception:
                    pass
    except Exception as e:
        print(f"[firecrawl] prior session cleanup skipped: {e}")


def _interact(app: Any, scrape_id: str, *, prompt: str, timeout: int = 120) -> Any:
    return app.interact(scrape_id, prompt=prompt, timeout=timeout)


def _urls_match(expected: str, actual: str) -> bool:
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
    """Crawl the exact job URL with Firecrawl, then LLM-fill via CDP Playwright."""
    from .agents import applier as ap

    ensure_playwright_browsers_path()
    key = firecrawl_api_key()
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY missing")

    from firecrawl import Firecrawl

    target = job_target(job)
    brief = _candidate_brief(job, profile, tailored)
    app = Firecrawl(api_key=key)
    # Never delete other Apply sessions.  Each run owns only the session it
    # creates below; the old sweep killed concurrent users' browsers.

    print(f"[firecrawl] scraping EXACT job URL (uncached):\n  {target}")
    if write_live:
        write_live(job, None, "opening", f"Firecrawl scrape → {target}", live_view_url="", engine="firecrawl")

    doc = app.scrape(
        target,
        formats=["markdown"],
        wait_for=3000,
        timeout=120_000,
        max_age=0,
        store_in_cache=False,
        profile={"name": _profile_name(), "save_changes": True},
    )
    scrape_id = _scrape_id(doc)
    if not scrape_id:
        raise RuntimeError("Firecrawl scrape returned no scrape_id — cannot interact")
    print(f"[firecrawl] scrape_id={scrape_id}")

    live = ""
    cdp = ""
    try:
        boot = _interact(
            app,
            scrape_id,
            prompt=(
                f"CRITICAL: Open exactly this URL and wait until the job page is fully loaded:\n{target}\n\n"
                "Do not search. Do not open a different job. Do not go to Home/Feed. "
                "Dismiss cookie banners. Reply with the final URL."
            ),
            timeout=120,
        )
        live = getattr(boot, "interactive_live_view_url", None) or getattr(boot, "live_view_url", None) or ""
        cdp = getattr(boot, "cdp_url", None) or ""
        print(f"[firecrawl] live view: {live or '(none)'}")
        if write_live:
            write_live(job, None, "loaded", f"Crawler on job page — clicking Apply", live_view_url=live, engine="firecrawl")

        apply_prompt = f"""You are applying to ONE specific job.

EXACT JOB URL (stay on this posting or its apply modal):
{target}

Candidate (use only these facts later when filling — for now just open the form):
{json.dumps(brief, ensure_ascii=False)[:3200]}

Steps NOW:
1. If not on that URL, navigate to it.
2. Click "Easy Apply" if present; else "Apply" / "Apply now" (never Save/Follow/Message).
3. If a sign-in wall appears, reply exactly: LOGIN_REQUIRED
4. Do NOT submit the application yet. Stop when the form/modal is open.
"""
        apply_res = _interact(app, scrape_id, prompt=apply_prompt, timeout=150)
        cdp = getattr(apply_res, "cdp_url", None) or cdp
        live = (
            getattr(apply_res, "interactive_live_view_url", None)
            or getattr(apply_res, "live_view_url", None)
            or live
        )
        blob = " ".join(
            str(x)
            for x in (
                getattr(apply_res, "result", None),
                getattr(apply_res, "stdout", None),
                getattr(apply_res, "output", None),
            )
            if x
        )
        if "LOGIN_REQUIRED" in blob.upper():
            if write_live:
                write_live(
                    job,
                    None,
                    "manual",
                    "Login required — use Firecrawl live view",
                    live_view_url=live,
                    engine="firecrawl",
                )
            return (
                "manual",
                "Firecrawl hit a login wall — sign in via the live view, then click Apply with agent again",
            )

        if not cdp:
            ping = _interact(app, scrape_id, prompt="Stay on the current page and report the URL.", timeout=60)
            cdp = getattr(ping, "cdp_url", None) or ""
            live = getattr(ping, "interactive_live_view_url", None) or live
        if not cdp:
            raise RuntimeError("Firecrawl interact did not return a cdp_url")

        deadline = time.time() + ap._apply_timeout_sec()
        print(f"[firecrawl] apply timeout={ap._apply_timeout_sec()}s")

        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(cdp)
            try:
                ctx = browser.contexts[0] if browser.contexts else browser.new_context(
                    viewport={"width": 1280, "height": 900}
                )
                page = ctx.pages[0] if ctx.pages else ctx.new_page()

                # If Easy Apply is already open, do NOT goto — that dismisses the modal.
                modal_open = False
                try:
                    modal_open = ap._easy_apply_modal_open(page)
                except Exception:
                    modal_open = False

                if modal_open:
                    print("[firecrawl] Easy Apply modal already open — skipping goto")
                    skip_goto = True
                else:
                    skip_goto = False
                    for attempt in range(2):
                        if machine is not None:
                            machine.check_cancel()
                        print(f"[firecrawl] forcing goto ({attempt + 1}/2) → {target}")
                        page.goto(target, wait_until="domcontentloaded", timeout=90_000)
                        ap.wait_for_page_ready(page, timeout_ms=8000)
                        if _urls_match(target, page.url or ""):
                            break
                print(f"[firecrawl] browser URL: {page.url}")

                if write_live:
                    write_live(
                        job,
                        page,
                        "filling",
                        f"Exact job loaded — LLM filling ({page.url})",
                        live_view_url=live,
                        engine="firecrawl",
                    )

                # Do NOT call Firecrawl interact while CDP is connected — it tears
                # down the remote page and causes "Target page has been closed".
                try:
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
                        skip_initial_goto=skip_goto,
                        machine=machine,
                    )
                except TimeoutError as e:
                    msg = str(e)
                    print(f"[firecrawl] {msg}")
                    if write_live:
                        write_live(job, None, "timeout", msg[:180], live_view_url=live, engine="firecrawl")
                    return "errors", msg
            finally:
                # Disconnect CDP client only — stop_interaction owns the remote browser.
                try:
                    browser.close()
                except Exception:
                    pass
    finally:
        try:
            app.stop_interaction(scrape_id)
        except Exception:
            pass
        if write_live:
            try:
                write_live(job, None, "done", "Firecrawl apply session closed", live_view_url="", engine="firecrawl")
            except Exception:
                pass
        print(f"[firecrawl] stopped interaction {scrape_id}")
