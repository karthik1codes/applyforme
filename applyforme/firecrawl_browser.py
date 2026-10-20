"""Firecrawl cloud browser for Apply — scrape/interact + CDP session for Playwright.

Requires FIRECRAWL_API_KEY (from `npx firecrawl-cli init --browser` or the dashboard).
Set APPLYFORME_APPLY_ENGINE=firecrawl|playwright (default playwright).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


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


@dataclass
class FirecrawlSession:
    id: str
    cdp_url: str
    live_view_url: str = ""
    interactive_live_view_url: str = ""
    client: Any = None

    def close(self) -> None:
        if not self.client or not self.id:
            return
        try:
            self.client.delete_browser(self.id)
        except Exception:
            pass


def open_apply_session(*, ttl_sec: int = 1800) -> FirecrawlSession:
    """Start a new Firecrawl browser without touching other apply sessions.

    The old implementation listed and deleted every active cloud browser on
    each run, which could kill a concurrent application.  Each session now owns
    only its own id and is closed in ``FirecrawlSession.close``.
    """
    key = firecrawl_api_key()
    if not key:
        raise RuntimeError(
            "FIRECRAWL_API_KEY missing — run `npx -y firecrawl-cli@latest init --all --browser` "
            "or paste a key from https://www.firecrawl.dev/app/api-keys into .env"
        )
    try:
        from firecrawl import Firecrawl
    except ImportError as e:
        raise RuntimeError("firecrawl-py not installed — pip install firecrawl-py") from e

    app = Firecrawl(api_key=key)
    profile_name = (os.getenv("FIRECRAWL_BROWSER_PROFILE") or "applyforme").strip() or "applyforme"
    session = app.browser(
        ttl=max(120, ttl_sec),
        profile={"name": profile_name, "save_changes": True},
    )
    sid = getattr(session, "id", None) or ""
    cdp = getattr(session, "cdp_url", None) or ""
    live = getattr(session, "live_view_url", None) or ""
    interactive = getattr(session, "interactive_live_view_url", None) or live
    if not sid or not cdp:
        raise RuntimeError(f"Firecrawl browser() returned incomplete session: {session!r}")
    return FirecrawlSession(
        id=sid,
        cdp_url=cdp,
        live_view_url=live,
        interactive_live_view_url=interactive or live,
        client=app,
    )
