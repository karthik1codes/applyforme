"""Tests for quality checks, routing/verification, location filtering, Workday parsing and the setup wizard."""
from __future__ import annotations

import yaml

from applyforme import quality, wizard
from applyforme.agents import discovery as D
from applyforme.agents import resume as R
from applyforme.agents import tailor as T
from applyforme.agents.routing import classify_submission, closed_reason, manual_reason
from applyforme.config import ROOT, load_profile
from applyforme.models import Job, Preferences, ResumeDoc, Tailored

GOOD_LETTER = ("Dear team, " + "I built ingestion pipelines that process millions of events a day and cut API latency by 40 percent. " * 5
               + "Jane Doe")


# ---- quality -------------------------------------------------------------------------------------------------
def test_sanitize_removes_machine_typography():
    s = quality.sanitize_text("Built it \u2014 fast. \u201cQuoted\u201d \u2013 range\u2026")
    assert "\u2014" not in s and "\u201c" not in s and "\u2026" not in s and '"Quoted"' in s


def test_cover_letter_validation():
    assert quality.validate_cover_letter(GOOD_LETTER, candidate_name="Jane Doe")[0] == []
    errs, _ = quality.validate_cover_letter("As an AI language model, I cannot write [Company Name] a letter.")
    assert any("assistant-style" in e for e in errs) and any("placeholder" in e for e in errs)
    assert any("too long" in e for e in quality.validate_cover_letter("word " * 400)[0])
    assert quality.validate_cover_letter(GOOD_LETTER + " I am passionate.")[1]  # cliche warning


def test_tailor_retries_with_fresh_prompt_then_succeeds(monkeypatch):
    calls: list[str] = []

    def fake(system, user, schema, temperature=0.2, **kw):
        calls.append(user)
        return Tailored(cover_letter="As an AI I cannot." if len(calls) == 1 else GOOD_LETTER)

    monkeypatch.setattr(T, "ask_json", fake)
    prof = load_profile(ROOT / "profile.example.yaml")
    out = T.tailor(Job(id="x:y:1", ats="x", company="Y", title="Eng", url="u"), prof, ["Python"])
    assert len(calls) == 2 and "rejected" in calls[1] and "As an AI" not in calls[1]
    assert out.cover_letter.startswith("Dear")


def test_tailor_gives_up_after_three_bad_drafts(monkeypatch):
    monkeypatch.setattr(T, "ask_json", lambda *a, **k: Tailored(cover_letter="too short"))
    prof = load_profile(ROOT / "profile.example.yaml")
    try:
        T.tailor(Job(id="x:y:1", ats="x", company="Y", title="Eng", url="u"), prof)
        raise AssertionError("should have raised")
    except RuntimeError as e:
        assert "3 attempts" in str(e)


def test_judge_rejects_resume_with_invented_work(monkeypatch):
    prof = load_profile(ROOT / "profile.example.yaml")
    base = R._baseline(prof)
    monkeypatch.setattr(R, "ask_json", lambda system, user, schema, **k:
                        R.Verdict(verdict="FAIL", issues=["claims team leadership not in original"]) if schema is R.Verdict else base.model_copy(deep=True))
    doc, errs = R.tailor_resume(Job(id="x:y:1", ats="x", company="Y", title="Eng", url="u", description="d"), prof, ["Python"])
    assert errs and errs[0].startswith("judge:") and doc == base  # fell back to the untouched original
    monkeypatch.setenv("APPLYFORME_JUDGE", "0")
    doc2, errs2 = R.tailor_resume(Job(id="x:y:1", ats="x", company="Y", title="Eng", url="u", description="d"), prof)
    assert errs2 == []


# ---- routing / verification ----------------------------------------------------------------------------------
def test_manual_routing():
    assert manual_reason("https://nvidia.wd5.myworkdayjobs.com/en-US/site/job/x")
    assert manual_reason("https://accounts.google.com/signin/v2")
    assert manual_reason("https://boards.greenhouse.io/stripe/jobs/1") is None
    assert manual_reason("https://notmyworkdayjobs.com.evil.example/x") is None  # host must END with the domain
    assert manual_reason("https://evil-icims.com/job") is None


def test_closed_detection():
    assert closed_reason("Sorry, this job is no longer accepting applications")
    assert closed_reason("The position has been filled")
    assert closed_reason("Senior Engineer - apply now, we are hiring") is None


def test_submission_classification_never_assumes_success():
    f = "https://x.com/apply"
    assert classify_submission("Thank you for applying! We have received your application.", f, f, 0) == "applied"
    assert classify_submission("Thanks!", f, "https://x.com/apply/confirmation", 0) == "applied"
    assert classify_submission("Please fix the errors below", f, f, 2) == "errors"
    assert classify_submission("Apply for this job", f, f, 0) == "unverified"  # nothing changed -> not proven
    assert classify_submission("Thank you for your interest in our footer", f, f, 0) == "unverified"


# ---- location filter -----------------------------------------------------------------------------------------
def test_location_filter_rejects_region_locked_remote():
    p = Preferences(locations=["Remote", "Bengaluru"], reject_locations=["US", "USA", "Canada"])
    ok = lambda s: D.location_ok(s, p)  # noqa: E731
    assert ok("Remote")
    assert ok("Bengaluru, India")
    assert ok("Bengaluru or Remote (US)")           # names an accepted place
    assert not ok("US-Remote")
    assert not ok("Remote - Canada")
    assert not ok("Toronto, Canada")
    assert not ok("London, UK")                       # not remote and not an accepted place
    assert ok("2 Locations")                          # Workday collapsed text: let the scorer decide
    assert not D.location_ok("Remote", Preferences(locations=["Bengaluru"]))
    assert not D.location_ok("Mumbai", Preferences(locations=["Remote"], remote_only=True))
    assert ok("Business Park, Remote")                # whole-word matching: 'US' must not match inside 'Business'


# ---- workday -------------------------------------------------------------------------------------------------
def test_workday_listing_dedupes_and_builds_urls(monkeypatch):
    pages = {
        0: {"total": 3, "jobPostings": [
            {"title": "Software Engineer", "externalPath": "/job/Pune/Software-Engineer_JR1", "locationsText": "Pune"},
            {"title": "SRE", "externalPath": "/job/Remote/SRE_JR2", "locationsText": "Remote"}]},
        20: {"total": 3, "jobPostings": []},
    }
    monkeypatch.setattr(D, "workday_search", lambda emp, q, offset=0, limit=20: pages.get(offset, {"jobPostings": []}))
    emp = {"name": "Acme", "base_url": "https://acme.wd1.myworkdayjobs.com/", "tenant": "acme", "site_id": "Careers"}
    jobs = D.workday(emp, ["software", "sre"])
    assert [j.id for j in jobs] == ["workday:acme:Software-Engineer_JR1", "workday:acme:SRE_JR2"]
    assert jobs[0].url == "https://acme.wd1.myworkdayjobs.com/en-US/Careers/job/Pune/Software-Engineer_JR1"
    assert jobs[0].company == "Acme"

    seen = {}
    monkeypatch.setattr(D, "workday_description", lambda emp, path: seen.setdefault("p", path) and "Build things")
    D.fill_workday_description(emp, jobs[0])
    assert seen["p"] == "/job/Pune/Software-Engineer_JR1" and jobs[0].description == "Build things"


# ---- setup wizard --------------------------------------------------------------------------------------------
def test_build_profile_merges_resume_and_answers():
    base = yaml.safe_load((ROOT / "profile.example.yaml").read_text(encoding="utf-8"))
    ex = wizard.ResumeExtract(first_name="Asha", last_name="Rao", email="asha@x.in", skills=["Go"],
                              experience=[wizard._Exp(company="Foo", title="SDE", start="2021-01", end="present", highlights=["Cut costs 30%"])])
    out = wizard.build_profile(ex, {"salary_expectation": "2400000", "salary_currency": "INR", "target_titles": ["SDE"],
                                    "locations": ["Remote"], "reject_locations": ["US"], "min_match_score": 60, "phone": ""}, base)
    assert out["personal"]["first_name"] == "Asha"
    assert out["personal"]["phone"] == base["personal"]["phone"]  # blank answer keeps the existing value
    assert out["experience"][0]["company"] == "Foo" and out["skills"] == ["Go"]
    assert out["compensation"]["salary_expectation"] == "2400000"
    assert out["preferences"]["reject_locations"] == ["US"] and out["preferences"]["min_match_score"] == 60
    assert out["sources"] == base["sources"]  # watched companies preserved
    from applyforme.models import Profile
    Profile(**out)  # result must be a loadable profile


def test_pdf_roundtrip_for_resume_import(tmp_path, monkeypatch):
    prof = load_profile(ROOT / "profile.example.yaml")
    monkeypatch.setattr(R, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(R, "tailor_resume", lambda job, p, kw=None: (R._baseline(p), []))
    pdf, _, _ = R.build_pdf(Job(id="a:b:1", ats="a", company="b", title="t", url="u"), prof)
    assert "Acme Corp" in wizard.pdf_text(__import__("pathlib").Path(pdf))
