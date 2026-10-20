"""Engine selection for LinkedIn / Firecrawl live-view login."""

from __future__ import annotations

from applyforme.firecrawl_browser import firecrawl_for_job


def test_headless_linkedin_uses_firecrawl_live_view(monkeypatch):
    monkeypatch.setenv("APPLYFORME_APPLY_ENGINE", "auto")
    monkeypatch.setenv("APPLYFORME_BROWSER_HEADED", "0")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.delenv("APPLYFORME_LINKEDIN_ENGINE", raising=False)

    assert firecrawl_for_job("https://www.linkedin.com/jobs/view/1")
    assert not firecrawl_for_job("https://www.glassdoor.com/job-listing/j?jl=1")


def test_headed_linkedin_keeps_the_local_browser(monkeypatch):
    monkeypatch.setenv("APPLYFORME_APPLY_ENGINE", "auto")
    monkeypatch.setenv("APPLYFORME_BROWSER_HEADED", "1")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.delenv("APPLYFORME_LINKEDIN_ENGINE", raising=False)

    assert not firecrawl_for_job("https://www.linkedin.com/jobs/view/1")


def test_linkedin_engine_override(monkeypatch):
    monkeypatch.setenv("APPLYFORME_APPLY_ENGINE", "auto")
    monkeypatch.setenv("APPLYFORME_BROWSER_HEADED", "0")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")

    monkeypatch.setenv("APPLYFORME_LINKEDIN_ENGINE", "playwright")
    assert not firecrawl_for_job("https://www.linkedin.com/jobs/view/1")

    monkeypatch.setenv("APPLYFORME_LINKEDIN_ENGINE", "firecrawl")
    assert firecrawl_for_job("https://www.linkedin.com/jobs/view/1")


def test_no_firecrawl_key_falls_back_to_local(monkeypatch):
    monkeypatch.setenv("APPLYFORME_APPLY_ENGINE", "auto")
    monkeypatch.setenv("APPLYFORME_BROWSER_HEADED", "0")
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("FIRECRAWL_KEY", raising=False)

    assert not firecrawl_for_job("https://www.linkedin.com/jobs/view/1")
