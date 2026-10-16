"""Junior seekers must not see senior/staff/lead roles."""
from applyforme.agents.discovery import prefilter
from applyforme.config import ROOT, load_profile
from applyforme.models import Job, Preferences
from applyforme.seniority import default_exclude_for, detect_title_level, normalize_level, seniority_ok


def _job(title: str) -> Job:
    return Job(id="t:c:1", ats="t", company="c", title=title, url="http://x", location="Remote")


def test_normalize_and_detect():
    assert normalize_level("jr") == "junior"
    assert normalize_level("entry-level") == "junior"
    assert detect_title_level("Senior Backend Engineer") == "senior"
    assert detect_title_level("Staff Software Engineer") == "lead"
    assert detect_title_level("Software Engineer") is None


def test_junior_blocks_senior_titles():
    assert not seniority_ok("Senior Software Engineer", "junior")
    assert not seniority_ok("Staff Engineer", "junior")
    assert not seniority_ok("Engineering Manager", "junior")
    assert not seniority_ok("Principal Engineer", "junior")
    assert seniority_ok("Software Engineer", "junior")
    assert seniority_ok("Junior Developer", "junior")
    assert seniority_ok("Associate Software Engineer", "junior")


def test_senior_blocks_intern_junior():
    assert not seniority_ok("Junior Developer", "senior")
    assert not seniority_ok("Software Engineering Intern", "senior")
    assert seniority_ok("Senior Backend Engineer", "senior")


def test_prefilter_respects_seniority(monkeypatch):
    prof = load_profile(ROOT / "profile.example.yaml")
    prof.preferences = Preferences(
        target_titles=["Software Engineer", "Developer"],
        seniority_level="junior",
        locations=["Remote"],
        exclude_keywords=[],
    )
    assert prefilter(_job("Software Engineer"), prof)
    assert not prefilter(_job("Senior Software Engineer"), prof)
    assert not prefilter(_job("Staff Frontend Engineer"), prof)
    assert "senior" in default_exclude_for("junior")
