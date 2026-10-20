"""Firecrawl cloud browser session lifecycle for Apply.

How Firecrawl's interact layer actually works (verified against the live API
with the shipped ``firecrawl-py`` SDK and the official endpoint docs):

* ``POST /v2/scrape`` returns ``data.metadata.scrapeId``.  A scrape that
  carries ``profile`` binds a **persistent browser profile** to that job.
* ``POST /v2/scrape/{scrapeId}/interact`` runs one action in the browser
  bound to that scrape.  The first call starts the browser session and every
  later call reuses it.  The response carries ``cdpUrl`` (raw Chrome DevTools
  Protocol websocket), ``liveViewUrl`` (watch only) and
  ``interactiveLiveViewUrl`` (the user can click/type in it).
* ``POST /v2/interact`` starts a **standalone** session with no prior scrape.
* ``DELETE /v2/scrape/{scrapeId}/interact`` stops a scrape-bound session.
* ``DELETE /v2/interact/{id}`` stops a standalone session.

The important, non-obvious rule: **a profile has exactly one writer.**
``profile.saveChanges = true`` takes an exclusive write lock on that profile
for the lifetime of the session.  Any second session on the same profile —
even a read-only one, even from another process — fails with::

    HTTP 409  Browser operation conflicts with the current session or profile state.

That 409 is the single most common way a Firecrawl Apply run dies: a previous
run crashed, was killed, or lost its ``finally`` cleanup, so its session kept
the write lock and every later run was rejected at the first ``interact`` call.

This module owns the session lifecycle so that:

* each run creates **one** session and always releases it in ``finally``;
* a session id is recorded in the shared SQLite store, so a run that dies
  without cleanup can be reclaimed by the next run instead of wedging the
  profile forever;
* a session is only ever reclaimed when it is provably stale (older than a
  grace period **and** not owned by a live run), never blindly sweeping every
  active session the way the old code did;
* the CDP url, live-view url and interactive live-view url are surfaced to
  the dashboard so the user can sign in to LinkedIn by hand.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

# A session is considered reclaimable only when it has been idle for longer
# than this.  Firecrawl's own inactivity TTL is 300s by default, so a session
# that has been quiet for longer than that is a leftover, not a live run.
STALE_SESSION_SEC = 900


def firecrawl_api_key() -> str:
    return (os.getenv("FIRECRAWL_API_KEY") or os.getenv("FIRECRAWL_KEY") or "").strip()


def apply_engine() -> str:
    """playwright | firecrawl — auto uses the local, observable browser by default.

    The Firecrawl path is still available with ``APPLYFORME_APPLY_ENGINE=firecrawl``
    (it needs an API key and a cloud session).  Auto deliberately prefers the
    local persistent browser: it is faster, keeps the LinkedIn session, and does
    not need the extra scrape/interact/CDP hop that caused target-page-closed
    races.
    """
    raw = (os.getenv("APPLYFORME_APPLY_ENGINE") or "auto").strip().lower()
    if raw in ("firecrawl", "fc", "cloud"):
        return "firecrawl"
    if raw in ("playwright", "local", "pw", "auto"):
        return "playwright"
    return "playwright"


def firecrawl_enabled() -> bool:
    return apply_engine() == "firecrawl" and bool(firecrawl_api_key())


def _headless() -> bool:
    return (os.getenv("APPLYFORME_BROWSER_HEADED", "1") or "").strip().lower() in (
        "0", "false", "no", "off",
    )


def firecrawl_for_job(url: str) -> bool:
    """Whether this job should use the Firecrawl browser.

    LinkedIn Easy Apply needs a signed-in web session.  A headless EC2 worker
    cannot show the login window, so use Firecrawl's live view for LinkedIn when
    a key is available; the user signs in once and the cloud profile keeps it.
    """
    if firecrawl_enabled():
        return True
    if "linkedin.com" not in (url or "").lower():
        return False
    mode = (os.getenv("APPLYFORME_LINKEDIN_ENGINE") or "auto").strip().lower()
    if mode in ("playwright", "local", "pw"):
        return False
    if mode in ("firecrawl", "fc", "cloud"):
        return bool(firecrawl_api_key())
    return bool(firecrawl_api_key()) and _headless()


def profile_name() -> str:
    """Name of the persistent Firecrawl browser profile.

    The profile stores the user's signed-in LinkedIn session between runs, so
    the name is stable on purpose.  It is also the unit that Firecrawl locks
    exclusively, which is why the lifecycle below is careful with it.
    """
    return (os.getenv("FIRECRAWL_BROWSER_PROFILE") or "applyforme").strip() or "applyforme"


def _session_client(key: str) -> Any:
    try:
        from firecrawl import Firecrawl
    except ImportError as e:  # pragma: no cover - dependency guard
        raise RuntimeError("firecrawl-py not installed — pip install firecrawl-py") from e
    return Firecrawl(api_key=key)


def _is_conflict(exc: BaseException) -> bool:
    """True for the HTTP 409 profile/session conflict."""
    msg = str(exc).lower()
    if "409" in msg:
        return True
    status = getattr(exc, "status_code", None)
    if status == 409:
        return True
    return "conflicts with the current session or profile state" in msg


def _is_rate_limited(exc: BaseException) -> bool:
    """True for Firecrawl's per-minute browser-session rate limit.

    Creating a browser session is rate limited (3/minute on the default plan),
    so a burst of Apply runs can hit it.  The error carries the reset time.
    """
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True
    msg = str(exc).lower()
    return "rate limit" in msg or "rate_limit" in msg


def _retry_after_seconds(exc: BaseException, default: float = 20.0) -> float:
    """Seconds to wait before retrying, from the error text when possible."""
    import re

    m = re.search(r"retry after (\d+)s", str(exc), re.I)
    if m:
        return min(120.0, max(1.0, float(m.group(1))))
    m = re.search(r"resets at ([0-9T:\-.Z:+ ]+)", str(exc))
    if m:
        from datetime import datetime, timezone

        raw = m.group(1).strip().replace(" GMT+0000", "").replace("UTC", "").strip()
        for fmt in ("%a %b %d %Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                when = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                delta = (when - datetime.now(timezone.utc)).total_seconds()
                if 0 < delta <= 180:
                    return min(120.0, delta + 2)
            except ValueError:
                continue
    return default


@dataclass
class FirecrawlSession:
    """A live Firecrawl browser session and the urls needed to use it."""

    id: str
    cdp_url: str
    live_view_url: str = ""
    interactive_live_view_url: str = ""
    profile: str = ""
    client: Any = None
    scrape_id: str = ""
    _released: bool = False

    def close(self) -> None:
        """Release the session so the profile write lock is freed.

        Safe to call twice.  Never raises: cleanup must not mask the real
        error that caused the run to end.
        """
        if self._released:
            return
        self._released = True
        if not self.client or not self.id:
            return
        try:
            if self.scrape_id:
                # Scrape-bound session: DELETE /v2/scrape/{scrapeId}/interact
                self.client.stop_interaction(self.scrape_id)
            else:
                # Standalone session: DELETE /v2/interact/{id}
                self.client.delete_browser(self.id)
        except Exception:
            pass


def reclaim_stale_sessions(
    app: Any,
    *,
    profile: str,
    store: Any = None,
    stale_sec: int = STALE_SESSION_SEC,
) -> list[str]:
    """Release leftover sessions that are holding the profile write lock.

    A run that crashed (killed process, power loss, unhandled exception before
    ``finally``) leaves its Firecrawl session alive, and that session keeps
    the profile locked.  Every later run then fails with HTTP 409 at its
    first ``interact`` call.  This reclaims only sessions that are provably
    abandoned:

    * the session is recorded in our own store (so we know it is ours),
    * it has been idle for longer than ``stale_sec``,
    * and no live run still claims it.

    Sessions belonging to other jobs, other profiles, or a run that is still
    going are never touched.  The old implementation deleted *every* active
    session, which killed concurrent users' browsers.
    """
    released: list[str] = []
    now = time.time()
    try:
        listed = app.list_browsers(status="active")
    except Exception:
        return released

    sessions = getattr(listed, "sessions", None) or []
    for s in sessions:
        sid = getattr(s, "id", None)
        if not sid:
            continue
        if store is not None and not store.firecrawl_session_is_stale(sid, stale_sec=stale_sec, now=now):
            continue
        if store is None:
            # No store: only reclaim a session nobody is using.
            continue
        try:
            app.delete_browser(sid)
            released.append(sid)
            print(f"[firecrawl] released stale session {sid}")
        except Exception:
            continue

    if store is not None and released:
        store.forget_firecrawl_sessions(released)
    return released


def open_apply_session(
    *,
    ttl_sec: int = 1800,
    store: Any = None,
    job_id: str = "",
) -> FirecrawlSession:
    """Start one standalone Firecrawl browser session with the apply profile.

    The session is recorded in the shared store before it is returned, so a
    crash cannot silently wedge the profile for every later run.  A stale
    session from a previous crashed run is reclaimed first.
    """
    key = firecrawl_api_key()
    if not key:
        raise RuntimeError(
            "FIRECRAWL_API_KEY missing — run `npx -y firecrawl-cli@latest init --all --browser` "
            "or paste a key from https://www.firecrawl.dev/app/api-keys into .env"
        )
    app = _session_client(key)
    prof = profile_name()

    # A crashed predecessor may still hold the profile write lock.
    reclaim_stale_sessions(app, profile=prof, store=store)

    def _create():
        return app.browser(
            ttl=max(120, ttl_sec),
            activity_ttl=max(120, int(ttl_sec / 2)),
            profile={"name": prof, "save_changes": True},
        )

    try:
        session = _create()
    except Exception as e:
        if _is_rate_limited(e):
            # Browser-session creation is rate limited per minute.  Wait it
            # out once instead of failing the whole application.
            wait = _retry_after_seconds(e)
            print(f"[firecrawl] rate limited — waiting {wait:.0f}s before retrying")
            time.sleep(wait)
            session = _create()
        elif _is_conflict(e):
            # Still conflicting: reclaim and try exactly once more.
            print("[firecrawl] profile busy — reclaiming stale sessions and retrying once")
            reclaim_stale_sessions(app, profile=prof, store=store, stale_sec=120)
            session = _create()
        else:
            raise

    sid = getattr(session, "id", None) or ""
    cdp = getattr(session, "cdp_url", None) or ""
    live = getattr(session, "live_view_url", None) or ""
    interactive = getattr(session, "interactive_live_view_url", None) or live
    if not sid or not cdp:
        raise RuntimeError(f"Firecrawl browser() returned incomplete session: {session!r}")

    if store is not None and job_id:
        try:
            store.remember_firecrawl_session(job_id, sid, prof)
        except Exception:
            pass

    return FirecrawlSession(
        id=sid,
        cdp_url=cdp,
        live_view_url=live,
        interactive_live_view_url=interactive or live,
        profile=prof,
        client=app,
    )
