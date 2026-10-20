"""Regression tests for the Firecrawl session lifecycle.

The bug these lock down: a Firecrawl browser profile has exactly one writer.
A session left alive by a crashed run kept the profile locked, so every later
run died with HTTP 409 at its first interact call — the "run it again and it
fails again" loop.

The tests use a fake Firecrawl client, so no network and no credits.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from applyforme import firecrawl_browser as fb  # noqa: E402
from applyforme.store import Store  # noqa: E402


class FakeSession:
    def __init__(self, sid: str, cdp: str, live: str = "https://live", interactive: str = "https://interactive"):
        self.id = sid
        self.cdp_url = cdp
        self.live_view_url = live
        self.interactive_live_view_url = interactive


class FakeClient:
    """Minimal stand-in for firecrawl.Firecrawl."""

    def __init__(self, *, conflict_until: set[str] | None = None):
        self.conflict_until = conflict_until or set()
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.active: dict[str, FakeSession] = {}
        self._n = 0

    def browser(self, **kwargs):
        profile = kwargs.get("profile") or {}
        name = profile.get("name") or ""
        if name in self.conflict_until:
            raise RuntimeError(
                "Unexpected error during create browser session: Status code 409. "
                "Browser operation conflicts with the current session or profile state."
            )
        self._n += 1
        sid = f"sess-{self._n}"
        sess = FakeSession(sid, f"wss://cdp/{sid}")
        self.created.append(sid)
        self.active[sid] = sess
        return sess

    def list_browsers(self, status=None):
        class Listed:
            pass

        out = Listed()
        out.sessions = list(self.active.values())
        return out

    def delete_browser(self, sid: str):
        if sid not in self.active:
            raise RuntimeError("unknown session")
        del self.active[sid]
        self.deleted.append(sid)
        return True

    def stop_interaction(self, job_id: str):
        self.deleted.append(job_id)
        return True


@pytest.fixture()
def store(tmp_path):
    s = Store(path=tmp_path / "t.db")
    yield s
    s.db.close()


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(fb, "_session_client", lambda key: client)
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")
    monkeypatch.setenv("FIRECRAWL_BROWSER_PROFILE", "applyforme-test")


def test_open_session_returns_cdp_and_live_views(monkeypatch, store):
    client = FakeClient()
    _patch_client(monkeypatch, client)

    sess = fb.open_apply_session(store=store, job_id="job-1")

    assert sess.id == "sess-1"
    assert sess.cdp_url == "wss://cdp/sess-1"
    assert sess.interactive_live_view_url == "https://interactive"
    assert sess.profile == "applyforme-test"
    # The session is recorded so a crash can be reclaimed later.
    assert store.firecrawl_session_is_stale("sess-1", stale_sec=0) is True


def test_session_close_releases_the_profile(monkeypatch, store):
    client = FakeClient()
    _patch_client(monkeypatch, client)

    sess = fb.open_apply_session(store=store, job_id="job-1")
    sess.close()

    assert "sess-1" in client.deleted
    # Closing twice must not raise.
    sess.close()


def test_conflict_reclaims_stale_session_and_retries(monkeypatch, store):
    """A leftover session must not wedge the profile forever."""
    client = FakeClient()
    _patch_client(monkeypatch, client)

    # Simulate a crashed predecessor: it left a recorded, idle session alive.
    client.active["sess-orphan"] = FakeSession("sess-orphan", "wss://cdp/orphan")
    store.remember_firecrawl_session("job-old", "sess-orphan", "applyforme-test")
    # Mark it as touched long ago so it counts as stale.
    store.db.execute(
        "UPDATE firecrawl_sessions SET last_seen_at=0 WHERE session_id=?", ("sess-orphan",)
    )
    store.db.commit()

    sess = fb.open_apply_session(store=store, job_id="job-2")

    assert "sess-orphan" in client.deleted
    assert sess.id  # a new session was created


def test_conflict_without_a_known_stale_session_still_raises(monkeypatch, store):
    client = FakeClient(conflict_until={"applyforme-test"})
    _patch_client(monkeypatch, client)

    with pytest.raises(Exception) as exc:
        fb.open_apply_session(store=store, job_id="job-3")
    assert "409" in str(exc.value)


def test_live_session_of_a_running_job_is_never_reclaimed(monkeypatch, store):
    """A concurrent run keeps its lock, so its session stays untouched."""
    client = FakeClient()
    _patch_client(monkeypatch, client)

    client.active["sess-live"] = FakeSession("sess-live", "wss://cdp/live")
    store.remember_firecrawl_session("job-live", "sess-live", "applyforme-test")
    store.db.execute("UPDATE firecrawl_sessions SET last_seen_at=0 WHERE session_id=?", ("sess-live",))
    store.db.commit()
    # The job is actively running: it holds the apply lock.
    store.acquire_apply_lock("job-live", "worker-1", ttl_sec=600)

    released = fb.reclaim_stale_sessions(client, profile="applyforme-test", store=store)

    assert released == []
    assert "sess-live" not in client.deleted


def test_untracked_sessions_are_never_reclaimed(monkeypatch, store):
    """A session we did not create is not ours to delete."""
    client = FakeClient()
    _patch_client(monkeypatch, client)

    client.active["sess-foreign"] = FakeSession("sess-foreign", "wss://cdp/foreign")

    released = fb.reclaim_stale_sessions(client, profile="applyforme-test", store=store)

    assert released == []
    assert "sess-foreign" not in client.deleted


def test_engine_selection_prefers_local_by_default(monkeypatch):
    monkeypatch.delenv("APPLYFORME_APPLY_ENGINE", raising=False)
    assert fb.apply_engine() == "playwright"
    monkeypatch.setenv("APPLYFORME_APPLY_ENGINE", "firecrawl")
    assert fb.apply_engine() == "firecrawl"
    monkeypatch.setenv("APPLYFORME_APPLY_ENGINE", "auto")
    assert fb.apply_engine() == "playwright"


def test_firecrawl_enabled_requires_a_key(monkeypatch):
    monkeypatch.setenv("APPLYFORME_APPLY_ENGINE", "firecrawl")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "")
    monkeypatch.delenv("FIRECRAWL_KEY", raising=False)
    assert fb.firecrawl_enabled() is False
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-abc")
    assert fb.firecrawl_enabled() is True


class RateLimitedClient(FakeClient):
    """Fails the first N session creations with the per-minute rate limit."""

    def __init__(self, failures: int = 1):
        super().__init__()
        self.failures = failures
        self.attempts = 0

    def browser(self, **kwargs):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise RuntimeError(
                "Rate Limit Exceeded: Failed to create browser session. Rate limit exceeded. "
                "Consumed (req/min): 3, Remaining (req/min): 0. ... please retry after 40s"
            )
        return super().browser(**kwargs)


def test_rate_limit_is_waited_out_then_retried(monkeypatch, store):
    """Browser-session creation is rate limited; the run must not die on it."""
    client = RateLimitedClient(failures=1)
    _patch_client(monkeypatch, client)
    slept: list[float] = []
    monkeypatch.setattr(fb.time, "sleep", lambda s: slept.append(s))

    sess = fb.open_apply_session(store=store, job_id="job-rl")

    assert sess.id
    assert client.attempts == 2
    assert slept and 1 <= slept[0] <= 120


def test_retry_after_is_parsed_from_the_error():
    exc = RuntimeError("Rate limit exceeded. please retry after 40s")
    assert fb._retry_after_seconds(exc) == 40.0


def test_rate_limit_and_conflict_are_distinguished():
    assert fb._is_rate_limited(RuntimeError("Rate Limit Exceeded: ...")) is True
    assert fb._is_conflict(RuntimeError("Rate Limit Exceeded: ...")) is False
    assert fb._is_conflict(RuntimeError("Status code 409. Browser operation conflicts")) is True
    assert fb._is_rate_limited(RuntimeError("Status code 409. Browser operation conflicts")) is False
