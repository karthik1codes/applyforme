"""Interactive setup: build profile.yaml from your real resume instead of hand-editing YAML.

`python -m applyforme setup --resume resume.pdf`
The LLM only EXTRACTS what's written in the resume (no inference); you confirm every field.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

import yaml
from pydantic import BaseModel

from .config import ROOT
from .llm import ask_json


class _Exp(BaseModel):
    company: str
    title: str
    start: str = ""
    end: str = ""
    highlights: list[str] = []


class _Edu(BaseModel):
    school: str = ""
    degree: str = ""
    year: str = ""


class ResumeExtract(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    summary: str = ""
    skills: list[str] = []
    experience: list[_Exp] = []
    education: list[_Edu] = []


EXTRACT_SYSTEM = """Extract structured data from a resume. You are a transcriber, not a writer.
- Copy text, employer names, titles and numbers EXACTLY as written. Never infer, embellish or add anything.
- Dates as YYYY-MM (or YYYY if only the year is given); use "present" for current roles. Leave unknown fields empty.
- `highlights` are the role's bullet points verbatim (one string each).
- `skills` only contains skills explicitly listed or clearly named in the resume.
- Most recent role first."""


def pdf_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_resume(path: Path) -> ResumeExtract:
    text = pdf_text(path).strip()
    if len(text) < 80:
        raise ValueError("couldn't read any text from the resume (scanned image PDF?)")
    return ask_json(EXTRACT_SYSTEM, text[:14000], ResumeExtract, temperature=0.0)


def _csv(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip() and x.strip() != "-"]


def build_profile(ex: ResumeExtract, answers: dict, base: dict) -> dict:
    """Merge extracted resume data + wizard answers over `base` (existing profile or example). Pure, unit-tested."""
    personal = {k: answers.get(k) or getattr(ex, k) or base.get("personal", {}).get(k, "")
                for k in ("first_name", "last_name", "email", "phone", "location", "linkedin", "github", "website")}
    screening = dict(base.get("screening", {}))
    screening.update(
        work_authorization=answers.get("work_authorization", screening.get("work_authorization", "")),
        requires_sponsorship=answers.get("requires_sponsorship", screening.get("requires_sponsorship", "No")),
        notice_period=answers.get("notice_period", screening.get("notice_period", "")),
        years_of_experience=answers.get("years_of_experience", screening.get("years_of_experience", "")),
        expected_salary=answers.get("salary_expectation", screening.get("expected_salary", "")),
    )
    comp = {
        "salary_currency": answers.get("salary_currency", "INR"),
        "salary_expectation": answers.get("salary_expectation", ""),
        "salary_range_min": answers.get("salary_range_min", answers.get("salary_expectation", "")),
        "salary_range_max": answers.get("salary_range_max", answers.get("salary_expectation", "")),
    }
    prefs = dict(base.get("preferences", {}))
    for k in ("target_titles", "locations", "reject_locations", "exclude_keywords"):
        if k in answers:
            prefs[k] = answers[k]
    if "min_match_score" in answers:
        prefs["min_match_score"] = answers["min_match_score"]
    out = dict(base)
    out.update(
        personal=personal,
        resume_path=answers.get("resume_path", base.get("resume_path", "./resume.pdf")),
        summary=ex.summary or base.get("summary", ""),
        skills=ex.skills or base.get("skills", []),
        experience=[e.model_dump() for e in ex.experience] or base.get("experience", []),
        education=[e.model_dump() for e in ex.education] or base.get("education", []),
        preferences=prefs,
        screening=screening,
        compensation=comp,
    )
    return out


def run(resume: str | None = None, use_ai: bool = True, ask: Callable[[str], str] = input) -> Path:
    target = ROOT / "profile.yaml"
    src = target if target.exists() else ROOT / "profile.example.yaml"
    base = yaml.safe_load(src.read_text(encoding="utf-8")) or {}

    def q(label: str, default: str = "") -> str:
        r = ask(f"{label}" + (f" [{default}]" if default else "") + ": ").strip()
        return r or default

    print("applyforme setup. Press Enter to keep the value shown in [brackets]; type - to clear a list.\n")
    rpath = Path(q("Path to your resume (PDF or .txt)", resume or base.get("resume_path", "./resume.pdf"))).expanduser()
    rpath = rpath if rpath.is_absolute() else (ROOT / rpath)
    ex = ResumeExtract()
    if rpath.exists() and use_ai:
        try:
            print("Reading your resume...")
            ex = extract_resume(rpath)
            print(f"  found {len(ex.experience)} roles, {len(ex.skills)} skills, {len(ex.education)} education entries")
        except Exception as e:
            print(f"  could not auto-import ({e}); continuing with manual answers")
    elif not rpath.exists():
        print(f"  {rpath} not found. Put your resume there before running `apply` (needed for uploads).")

    bp = base.get("personal", {})
    ans: dict = {"resume_path": str(rpath.relative_to(ROOT)) if rpath.is_relative_to(ROOT) else str(rpath)}
    print("\n-- Contact (check these carefully, they go on every application) --")
    for k, label in [("first_name", "First name"), ("last_name", "Last name"), ("email", "Email"), ("phone", "Phone"),
                     ("location", "Location"), ("linkedin", "LinkedIn URL"), ("github", "GitHub URL"), ("website", "Website")]:
        ans[k] = q(label, getattr(ex, k) or bp.get(k, ""))
    print("\n-- Compensation and eligibility --")
    bs, bc = base.get("screening", {}), base.get("compensation", {})
    ans["salary_currency"] = q("Salary currency", bc.get("salary_currency", "INR"))
    ans["salary_expectation"] = q("Expected annual salary (number)", str(bc.get("salary_expectation", "")))
    ans["salary_range_min"] = q("Lowest acceptable annual salary", str(bc.get("salary_range_min") or ans["salary_expectation"]))
    ans["salary_range_max"] = q("Upper end of your range", str(bc.get("salary_range_max") or ans["salary_expectation"]))
    ans["work_authorization"] = q("Work authorization answer", bs.get("work_authorization", ""))
    ans["requires_sponsorship"] = q("Need visa sponsorship?", bs.get("requires_sponsorship", "No"))
    ans["notice_period"] = q("Notice period", bs.get("notice_period", ""))
    ans["years_of_experience"] = q("Total years of experience", str(bs.get("years_of_experience", "")))
    print("\n-- What to look for --")
    bpref = base.get("preferences", {})
    ans["target_titles"] = _csv(q("Target job titles (comma separated)", ", ".join(bpref.get("target_titles", []))))
    ans["locations"] = _csv(q("Accepted locations (include Remote if you want remote roles)", ", ".join(bpref.get("locations", []))))
    ans["reject_locations"] = _csv(q("Reject if location mentions (e.g. roles limited to a country you can't work in)",
                                     ", ".join(bpref.get("reject_locations", [])) or "US, USA, United States, Canada, UK, Europe"))
    ans["exclude_keywords"] = _csv(q("Skip titles containing", ", ".join(bpref.get("exclude_keywords", []))))
    ans["min_match_score"] = int(q("Minimum match score to pursue (0-100)", str(bpref.get("min_match_score", 70))) or 70)

    prof = build_profile(ex, ans, base)
    if target.exists():
        shutil.copy(target, target.with_suffix(".yaml.bak"))
        print(f"\nBacked up the previous profile to {target.with_suffix('.yaml.bak').name}")
    header = "# Generated by `applyforme setup`. This is the ONLY source of truth the agents use; edit freely.\n"
    target.write_text(header + yaml.safe_dump(prof, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote {target}. Review the experience section, since resume text extraction can't be perfect.")
    return target
