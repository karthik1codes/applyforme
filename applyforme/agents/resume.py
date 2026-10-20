"""Resume agent: per-job tailored resume (reorder/emphasize, never fabricate) rendered to PDF."""
from __future__ import annotations

import os
import re

from playwright.sync_api import sync_playwright
from pydantic import BaseModel

from ..config import OUTPUT_DIR
from ..llm import ask_json
from ..models import Job, Profile, ResumeDoc, ResumeRole
from ..quality import sanitize_text

SYSTEM = """You tailor a candidate's resume to a specific job.
YOU MAY: reorder roles' bullets and skills by relevance, drop the least relevant bullets, reword bullets to
use the job's keywords WHEN the keyword truthfully describes the same work, rewrite the summary (max 3 sentences).
YOU MAY NOT: add skills, tools, employers, titles, dates, degrees, responsibilities or numbers that are not in the
profile. Keep every company, title, start and end EXACTLY as given. Metrics must be copied exactly.
Education, projects, honors/awards, and custom sections are taken verbatim from the profile for the PDF — do not
invent those; only return summary, skills, and experience in your JSON."""


def _baseline(profile: Profile) -> ResumeDoc:
    flat_skills = list(profile.skills)
    if not flat_skills and profile.skill_categories:
        for c in profile.skill_categories:
            items = c.get("items") or []
            if isinstance(items, str):
                items = [s.strip() for s in items.split(",") if s.strip()]
            flat_skills.extend(str(i) for i in items if i)
    return ResumeDoc(
        summary=profile.summary.strip(),
        skills=flat_skills,
        experience=[
            ResumeRole(
                company=e["company"],
                title=e["title"],
                location=str(e.get("location", "")),
                start=str(e.get("start", "")),
                end=str(e.get("end", "")),
                bullets=e.get("highlights", e.get("bullets", [])),
            )
            for e in profile.experience
        ],
    )


def _nums(s: str) -> set[str]:
    return set(re.findall(r"\d[\d,.]*%?", s))


def validate(doc: ResumeDoc, profile: Profile) -> list[str]:
    """Return a list of violations; empty means the tailored resume is faithful to the profile."""
    errs: list[str] = []
    base = {e["company"].lower(): e for e in profile.experience}
    if {r.company.lower() for r in doc.experience} - set(base):
        errs.append("unknown employer")
    for r in doc.experience:
        o = base.get(r.company.lower())
        if not o:
            continue
        if r.title != o["title"] or r.start != str(o.get("start", "")) or r.end != str(o.get("end", "")):
            errs.append(f"title/date changed for {r.company}")
        allowed = _nums(" ".join(o.get("highlights", [])))
        for b in r.bullets:
            if _nums(b) - allowed:
                errs.append(f"new number in bullet: {b[:60]}")
    allowed_skills = {s.lower() for s in profile.skills}
    if any(s.lower() not in allowed_skills for s in doc.skills):
        errs.append("skill not in profile")
    return errs


class Verdict(BaseModel):
    verdict: str  # PASS | FAIL
    issues: list[str] = []


JUDGE_SYSTEM = """You audit a tailored resume against the candidate's ORIGINAL resume data for fabrication.
FAIL if the tailored version claims any work, responsibility, tool, scope, team size, outcome or seniority that the
original does not support, even if reworded cleverly. Reordering, trimming and swapping in the job's wording for
the SAME work is fine. Reply with verdict PASS or FAIL and list each concrete problem in `issues`."""


def judge_enabled() -> bool:
    # Off by default — second LLM pass roughly doubles tailor time. Set APPLYFORME_JUDGE=1 to enable.
    return os.getenv("APPLYFORME_JUDGE", "0").strip().lower() in ("1", "true", "yes", "on")


def judge_resume(base: ResumeDoc, doc: ResumeDoc) -> list[str]:
    """Second LLM pass that catches invented work the regex-style validator can't see. Returns issues (empty = pass)."""
    user = f"ORIGINAL:\n{base.model_dump_json()}\n\nTAILORED:\n{doc.model_dump_json()}"
    try:
        v = ask_json(JUDGE_SYSTEM, user, Verdict, temperature=0.0)
    except Exception:
        return []  # judge is best-effort; the deterministic validator already passed
    return [] if v.verdict.strip().upper() == "PASS" else (v.issues or ["judge rejected the tailored resume"])


def _clean(doc: ResumeDoc) -> ResumeDoc:
    doc.summary = sanitize_text(doc.summary)
    for r in doc.experience:
        r.bullets = [sanitize_text(b) for b in r.bullets]
    return doc


def tailor_resume(job: Job, profile: Profile, keywords: list[str] | None = None) -> tuple[ResumeDoc, list[str]]:
    base = _baseline(profile)
    user = f"PROFILE:\n{base.model_dump_json()}\n\nJOB: {job.title} at {job.company}\n{job.description[:6000]}"
    if keywords:
        user += f"\n\nATS KEYWORDS the candidate truthfully has (mirror their wording where it describes the same work): {', '.join(keywords[:15])}"
    try:
        doc = _clean(ask_json(SYSTEM, user, ResumeDoc, temperature=0.3))
    except Exception as e:
        return base, [f"LLM failed: {e}"]
    errs = validate(doc, profile)
    if not errs and judge_enabled():
        errs = [f"judge: {i}" for i in judge_resume(base, doc)]
    return (base, errs) if errs else (doc, [])


def render_html(doc: ResumeDoc, profile: Profile) -> str:
    """Jake-style academic resume HTML (used for the PDF uploaded to application forms)."""
    from ..templates.elegant_resume import render_elegant_html

    return render_elegant_html(doc, profile)


_TEX_ESC = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    "\u2013": "--", "\u2014": "---", "\u2018": "'", "\u2019": "'", "\u201c": "``", "\u201d": "''", "\u2022": r"\textbullet{}",
}


def tex(s: object) -> str:
    """Escape text for LaTeX."""
    return "".join(_TEX_ESC.get(c, c) for c in str(s))


def render_latex(doc: ResumeDoc, profile: Profile) -> str:
    """Jake-style academic LaTeX — single-column, Times, Overleaf-ready single file."""
    from ..templates.elegant_resume import render_elegant_latex

    return render_elegant_latex(doc, profile)


def build_pdf(job: Job, profile: Profile, keywords: list[str] | None = None) -> tuple[str, str, list[str]]:
    """Tailor + render. Returns (pdf_path, tex_path, warnings)."""
    import time

    t0 = time.perf_counter()
    print(f"[resume] LLM tailor…")
    doc, errs = tailor_resume(job, profile, keywords)
    print(f"[resume] LLM done in {time.perf_counter() - t0:.1f}s" + (" (judge on)" if judge_enabled() else ""))
    stem = job.id.replace(":", "_")
    tex_path = OUTPUT_DIR / f"{stem}.resume.tex"
    tex_path.write_text(render_latex(doc, profile), encoding="utf-8")
    out = OUTPUT_DIR / f"{stem}.resume.pdf"
    t1 = time.perf_counter()
    print("[resume] rendering PDF via Chromium…")
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_page()
        pg.set_content(render_html(doc, profile), wait_until="domcontentloaded")
        pg.pdf(
            path=str(out),
            format="Letter",
            print_background=True,
            display_header_footer=False,
            margin={"top": "0.5in", "bottom": "0.5in", "left": "0.55in", "right": "0.55in"},
        )
        b.close()
    print(f"[resume] PDF ready in {time.perf_counter() - t1:.1f}s → {out}")
    return str(out), str(tex_path), errs
