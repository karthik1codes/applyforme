"""Budget / cache helpers (no live network)."""
import applyforme.crustdata as cd
from applyforme.models import Job


def test_needs_enrich_skips_when_website_present():
    j = Job(
        id="t:1",
        ats="indeed",
        company="Acme",
        title="SWE",
        url="https://example.com/j",
        company_website="https://acme.test",
        careers_url="https://acme.test/careers",
    )
    assert cd._needs_company_enrich(j) is False


def test_reset_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(cd, "_CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(cd, "_cache", None)
    monkeypatch.setenv("CRUSTDATA_MAX_CREDITS_PER_RUN", "10")
    monkeypatch.setenv("CRUSTDATA_MAX_ENRICH_PER_RUN", "2")
    cd.reset_run_budget()
    assert cd.credits_spent() == 0
    assert cd._charge(2.0, "test") is True
    assert cd.credits_spent() == 2.0
    assert cd._charge(9.0, "too much") is False


def test_job_search_off_by_default(monkeypatch):
    monkeypatch.setenv("CRUSTDATA_API_KEY", "cd_test")
    monkeypatch.delenv("CRUSTDATA_JOB_SEARCH", raising=False)
    assert cd.job_search_enabled() is False
    monkeypatch.setenv("CRUSTDATA_JOB_SEARCH", "1")
    assert cd.job_search_enabled() is True
