"""Retention, cross-board dedupe, and internship relevance.

These are the guarantees the dashboard relies on: the boards only keep roles
the agent has seen recently (or that the user has acted on), and off-target
internships never reach the matcher.
"""
from applyforme.agents.discovery import (
    effective_titles,
    internship_prefilter,
    sanitized_titles,
)
from applyforme.models import Job, Preferences, Profile
from applyforme.store import Store

OLD = "2020-01-01T00:00:00+00:00"


def _job(job_id: str, title: str, company: str = "Acme") -> Job:
    return Job(
        id=job_id, ats="test", company=company, title=title,
        location="Bengaluru", url=f"https://example.test/{job_id}",
    )


def _profile(titles: list[str] | None = None, skills: list[str] | None = None) -> Profile:
    return Profile(
        personal={},
        resume_path="./resume.pdf",
        skills=skills or ["Python", "SQL"],
        preferences=Preferences(
            target_titles=titles if titles is not None else ["Data Analyst"],
            search_focus="internships",
            locations=["Bengaluru", "Remote"],
        ),
    )


def test_placeholder_titles_fall_back_to_real_queries():
    assert sanitized_titles(["none", "N/A", " ", "Data Analyst"]) == ["Data Analyst"]
    assert effective_titles(_profile(titles=["none"], skills=[]))[0] == "software engineer"
    assert effective_titles(_profile(titles=["Data Analyst"])) == ["Data Analyst"]


def test_off_target_internships_are_rejected():
    p = _profile(["Data Analyst", "Software Engineer"], ["Python", "SQL"])
    keep = [
        "Data Analyst Intern",
        "AI Engineer Intern",
        "Junior Backend Engineer Intern",
        "Software Engineering Intern - Frontend (React.js)",
    ]
    drop = [
        "Marketing Intern - AI Video",
        "Graphic Design Intern",
        "Sales Internship",
        "Mechanical Design Apprentice",
        "Investment Banker Internship",
    ]
    assert all(internship_prefilter(_job(t, t), p) for t in keep)
    assert not any(internship_prefilter(_job(t, t), p) for t in drop)


def test_same_role_with_company_variant_is_not_inserted_twice(tmp_path):
    s = Store(tmp_path / "afm.db")
    assert s.add_job(_job("a", "AI Ops Intern", "Kuku")) is True
    assert s.add_job(_job("b", "AI Ops Intern", "Kuku Fm")) is False
    assert s.db.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"] == 1


def test_dedupe_keeps_the_row_with_progress(tmp_path):
    s = Store(tmp_path / "afm.db")
    j = _job("a", "AI Ops Intern", "Kuku")
    s.add_job(j)
    s.db.execute(
        "INSERT INTO jobs (id, company, title, url, job_json, status, updated_at, category, last_seen_at, dedupe_key)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("b", "Kuku Fm", "AI Ops Intern", "https://example.test/b", j.model_dump_json(), "skipped",
         OLD, "Internship", OLD, "ai ops intern|kuku fm"),
    )
    s.db.commit()
    removed = s.dedupe_jobs()
    assert removed == ["a"]
    left = s.db.execute("SELECT id, status FROM jobs").fetchall()
    assert [(r["id"], r["status"]) for r in left] == [("b", "skipped")]


def test_prune_drops_stale_untouched_but_keeps_user_progress(tmp_path):
    s = Store(tmp_path / "afm.db")
    for i, status in enumerate(["new", "matched", "skipped", "applied", "ready", "manual"]):
        job = _job(f"j{i}", f"Role {i}", f"Company {i}")
        s.add_job(job)
        s.update(job.id, status=status)
        s.db.execute("UPDATE jobs SET last_seen_at=? WHERE id=?", (OLD, job.id))
    s.db.commit()

    assert set(s.prune_stale(days=10)) == {"j0", "j1", "j2"}
    assert [r["id"] for r in s.db.execute("SELECT id FROM jobs ORDER BY id")] == ["j3", "j4", "j5"]
    assert s.prune_stale(days=0) == []  # disabled
