"""Job board searches are always on — never an empty/optional path."""
from applyforme.agents.discovery import ensure_searches
from applyforme.config import ROOT, load_profile
from applyforme.models import DEFAULT_BOARD_SITES, Preferences, Profile, Search


def test_default_sites_cover_all_boards():
    assert set(DEFAULT_BOARD_SITES) == {"indeed", "linkedin", "glassdoor", "zip_recruiter", "google"}


def test_ensure_searches_builds_from_target_titles():
    p = load_profile(ROOT / "profile.example.yaml")
    p.searches = []
    p.preferences = Preferences(
        target_titles=["Junior Developer", "Software Engineer"],
        locations=["Bengaluru", "Remote"],
        seniority_level="junior",
    )
    built = ensure_searches(p)
    assert [s.term for s in built] == ["Junior Developer", "Software Engineer"]
    assert built[0].location == "Bengaluru"
    assert set(built[0].sites) == set(DEFAULT_BOARD_SITES)


def test_ensure_searches_fills_empty_sites_on_existing():
    p = Profile(
        personal={"first_name": "A", "last_name": "B", "email": "a@b.c"},
        resume_path="./resume.pdf",
        searches=[Search(term="SDE", location="Remote", sites=[])],
    )
    out = ensure_searches(p)
    assert out[0].sites == list(DEFAULT_BOARD_SITES)
