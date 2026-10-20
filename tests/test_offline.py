"""Offline sanity tests (no API key needed). Run: .venv\\Scripts\\python -m pytest tests -q"""
import copy
from pathlib import Path

from applyforme import store as store_mod
from applyforme.agents import resume as R
from applyforme.agents.enrich import _jsonld
from applyforme.categories import categorize
from applyforme.config import ROOT, load_profile
from applyforme.inbox import classify
from applyforme.models import Job, ResumeRole


def _profile():
    return load_profile(ROOT / "profile.example.yaml")


def test_validator_accepts_baseline_and_rejects_fabrication():
    p = _profile()
    base = R._baseline(p)
    assert R.validate(base, p) == []

    bad = copy.deepcopy(base)
    bad.experience[0].bullets.append("Cut costs by 73%")  # invented metric
    assert any("new number" in e for e in R.validate(bad, p))

    bad = copy.deepcopy(base)
    bad.skills.append("Kubernetes")  # skill not in profile
    assert any("skill" in e for e in R.validate(bad, p))

    bad = copy.deepcopy(base)
    bad.experience.append(ResumeRole(company="Google", title="CEO"))
    assert any("employer" in e for e in R.validate(bad, p))

    bad = copy.deepcopy(base)
    bad.experience[0].title = "Principal Engineer"
    assert any("title/date" in e for e in R.validate(bad, p))


def test_render_pdf_and_tex(tmp_path, monkeypatch):
    p = _profile()
    monkeypatch.setattr(R, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(R, "tailor_resume", lambda job, prof, kw=None: (R._baseline(prof), []))
    job = Job(id="x:y:1", ats="x", company="y", title="t", url="http://x")
    pdf, tex_path, warns = R.build_pdf(job, p)
    assert Path(pdf).read_bytes()[:4] == b"%PDF" and warns == []
    src = Path(tex_path).read_text(encoding="utf-8")
    assert src.startswith("%") and r"\begin{document}" in src and r"\end{document}" in src
    assert "Acme Corp" in src and "Jane" in src
    # Elegant Resume (Jake-style) markers
    assert r"\usepackage{enumitem}" in src and r"\resumeItemListStart" in src and r"\href{" in src
    assert r"\resumeSection{Skills}" in src and r"\resumeSection{Experience}" in src


def test_latex_escaping():
    assert R.tex("R&D 100% #1 a_b $5 {x}") == r"R\&D 100\% \#1 a\_b \$5 \{x\}"
    assert "\\&" in R.tex("A & B") and R.tex("a\\b") == r"a\textbackslash{}b"


def test_categories():
    assert categorize("Senior Backend Engineer, Payments") == "Backend"
    assert categorize("Machine Learning Engineer") == "Machine Learning / AI"
    assert categorize("Data Engineer") == "Data"
    assert categorize("iOS Developer") == "Mobile"
    assert categorize("Engineering Manager, Platform") == "Engineering Management"
    assert categorize("Frontend Engineer") == "Frontend"
    assert categorize("Chief of Staff") == "Other"


def test_store_questions_events_kv(tmp_path, monkeypatch):
    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    s = store_mod.Store()
    job = Job(id="g:a:1", ats="g", company="a", title="Backend Engineer", url="http://x")
    assert s.add_job(job) and not s.add_job(job)
    assert s.get(job.id)["category"] == "Backend"

    s.save_questions(job.id, [{"label": "Salary?", "type": "text", "options": [], "suggested": None}])
    s.save_questions(job.id, [{"label": "Salary?", "type": "text"}])  # duplicate ignored
    assert s.get_answers(job.id) == {}
    s.db.execute("UPDATE questions SET answer='20 LPA' WHERE job_id=?", (job.id,))
    assert s.get_answers(job.id) == {"Salary?": "20 LPA"}
    assert s.db.execute("SELECT COUNT(*) c FROM questions").fetchone()["c"] == 1

    s.add_event(job.id, "submitted", "done", ref="r1")
    s.add_event(job.id, "submitted", "done", ref="r1")  # same ref deduped
    assert s.db.execute("SELECT COUNT(*) c FROM events").fetchone()["c"] == 1

    s.kv_set("k", "v1"); s.kv_set("k", "v2")
    assert s.kv_get("k") == "v2" and s.kv_get("nope") is None


def test_inbox_classifier():
    assert classify("Unfortunately we are not moving forward") == "rejection"
    assert classify("We'd like to schedule an interview") == "interview"
    assert classify("Thank you for applying to Acme") == "confirmation"
    assert classify("Hello there") == "reply"


def test_jsonld_extraction():
    page = '<script type="application/ld+json">{"@type":"JobPosting","description":"<p>Build things</p>"}</script>'
    assert _jsonld(page) == "Build things"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
