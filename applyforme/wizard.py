"""Interactive setup: build profile.yaml from your real resume instead of hand-editing YAML.

`python -m applyforme setup --resume resume.pdf`
The LLM only EXTRACTS what's written in the resume (no inference); you confirm every field.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Callable

import yaml
from pydantic import BaseModel, Field

from .config import ROOT
from .llm import ask_json

_PLACEHOLDER_RE = re.compile(
    r"example\.com|janedoe|johndoe|localhost|your[\s_-]?name|xxx+|TODO|placeholder",
    re.I,
)
_LINK_LABELS = frozenset({"github", "portfolio", "linkedin", "twitter", "website", "x", "link", "url"})


class _Exp(BaseModel):
    company: str = ""
    title: str = ""
    location: str = ""
    start: str = ""
    end: str = ""
    highlights: list[str] = []


class _Edu(BaseModel):
    school: str = ""
    degree: str = ""
    location: str = ""
    year: str = ""
    dates: str = ""
    field: str = ""
    details: str = ""
    gpa: str = ""


class _Project(BaseModel):
    name: str = ""
    tagline: str = ""
    description: str = ""
    links: str = ""
    bullets: list[str] = []


class _SkillCat(BaseModel):
    name: str = ""
    items: list[str] = []


class _CustomSection(BaseModel):
    """Any resume section that is not experience/education/skills/projects/honors."""

    title: str = ""
    bullets: list[str] = []


class ResumeExtract(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""
    portfolio: str = ""
    twitter: str = ""
    summary: str = ""
    skills: list[str] = []
    skill_categories: list[_SkillCat] = Field(default_factory=list)
    experience: list[_Exp] = []
    education: list[_Edu] = []
    projects: list[_Project] = Field(default_factory=list)
    honors: list[str] = Field(default_factory=list)
    custom_sections: list[_CustomSection] = Field(default_factory=list)


EXTRACT_SYSTEM = """Extract structured data from a resume. You are a transcriber, not a writer.

RULES (strict):
- Copy names, emails, phones, URLs, employer names, titles, schools, degrees, dates, metrics,
  and bullet text EXACTLY as written. Never invent, infer, embellish, paraphrase, or "improve".
- If a field is missing on the resume, leave it empty. Do not guess.
- Split the person's name into first_name / last_name exactly as shown (keep middle names in first_name if present).
- Dates: keep the resume's wording when possible (e.g. "Jan 2021 – Present"); otherwise YYYY-MM / YYYY; use "present" for current roles.
- experience.highlights = each bullet under that role, verbatim (one string per bullet).
- education: include school, degree, location, dates/year, GPA/details/field if shown.
- projects: name, short tagline/description if shown, links (URLs or "GitHub | Demo"), bullets verbatim.
- honors: every honor, award, scholarship, or recognition line verbatim (include the section's items even if titled Awards / Achievements).
- skills: flat list of every skill named. If the resume groups skills (Languages / Frameworks / Tools), ALSO fill skill_categories with those groups (name + items) while keeping the flat skills list complete.
- custom_sections: any other titled section (Certifications, Publications, Volunteer, Leadership, Coursework, Interests, Languages, etc.) with title + bullets/items verbatim. Do NOT put Experience, Education, Skills, Projects, or Honors/Awards here.
- Socials: linkedin, github, website, portfolio, twitter — ONLY real URLs or path-style handles
  (e.g. linkedin.com/in/…). Never put bare labels like "GitHub" or "Portfolio" in those fields.
- summary: ONLY if the resume has an explicit Summary / Objective / Profile paragraph. Otherwise leave empty — never invent one.
- Most recent experience and education first.
- Preserve every role, school, project, honor, and custom-section item — do not drop entries to "summarize"."""


def pdf_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def pdf_uris(path: Path) -> list[str]:
    """Collect clickable hyperlink URIs from a PDF (often where Portfolio/GitHub actually point)."""
    if path.suffix.lower() != ".pdf":
        return []
    from pypdf import PdfReader

    urls: list[str] = []
    try:
        reader = PdfReader(str(path))
    except Exception:
        return []
    for page in reader.pages:
        try:
            annots = page.get("/Annots") or []
        except Exception:
            continue
        for annot in annots:
            try:
                obj = annot.get_object()
                action = obj.get("/A") or {}
                uri = action.get("/URI")
                if uri:
                    urls.append(str(uri))
            except Exception:
                continue
    # Dedupe, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def clean_contact(val: str, kind: str = "") -> str:
    """Drop placeholders and bare link labels that are not real contact values."""
    v = (val or "").strip()
    if not v or _PLACEHOLDER_RE.search(v):
        return ""
    if kind in ("linkedin", "github", "website", "portfolio", "twitter"):
        if v.lower() in _LINK_LABELS:
            return ""
        # Require URL-ish shape; allow bare linkedin.com/... handles
        low = v.lower()
        if not (
            low.startswith("http://")
            or low.startswith("https://")
            or low.startswith("www.")
            or "linkedin.com" in low
            or "github.com" in low
            or "twitter.com" in low
            or "x.com/" in low
            or "." in v
        ):
            return ""
        if not v.startswith("http") and ("linkedin.com" in low or "github.com" in low or "twitter.com" in low or "x.com/" in low):
            v = "https://" + v.lstrip("/")
    return v


def _is_github_profile(uri: str) -> bool:
    return bool(re.match(r"https?://(www\.)?github\.com/[^/]+/?$", uri.strip(), re.I))


def _apply_pdf_uris(ex: ResumeExtract, uris: list[str]) -> ResumeExtract:
    """Fill empty social fields and project links from PDF hyperlink annotations."""
    data = ex.model_dump()
    for uri in uris:
        low = uri.lower()
        if low.startswith("mailto:") and not data.get("email"):
            data["email"] = uri.split(":", 1)[1]
            continue
        if "linkedin.com" in low and not clean_contact(data.get("linkedin", ""), "linkedin"):
            data["linkedin"] = uri
        elif _is_github_profile(uri) and not clean_contact(data.get("github", ""), "github"):
            data["github"] = uri
        elif ("twitter.com" in low or "x.com/" in low) and not clean_contact(data.get("twitter", ""), "twitter"):
            data["twitter"] = uri
        elif low.startswith("http") and "linkedin.com" not in low and "github.com" not in low:
            if not clean_contact(data.get("portfolio", ""), "portfolio"):
                data["portfolio"] = uri
            elif not clean_contact(data.get("website", ""), "website"):
                data["website"] = uri

    for k in ("linkedin", "github", "website", "portfolio", "twitter", "email", "phone"):
        if k in data:
            data[k] = clean_contact(str(data[k]), k if k != "email" else "")

    # Mirror portfolio ↔ website when only one is set (templates accept either).
    if data.get("portfolio") and not data.get("website"):
        data["website"] = data["portfolio"]
    elif data.get("website") and not data.get("portfolio"):
        data["portfolio"] = data["website"]

    used = {
        data.get("github") or "",
        data.get("website") or "",
        data.get("portfolio") or "",
        data.get("linkedin") or "",
    }
    rest = [
        u
        for u in uris
        if u not in used and not u.lower().startswith("mailto:") and not _is_github_profile(u)
    ]

    def _name_key(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (name or "").lower())

    def _uri_score(uri: str, key: str) -> int:
        if not key or len(key) < 4:
            return 0
        slug = re.sub(r"[^a-z0-9]", "", uri.lower())
        seg = re.sub(r"[^a-z0-9]", "", uri.rstrip("/").split("/")[-1].lower())
        if key in slug or (seg and (key in seg or seg in key)):
            return 3
        if key[:5] in slug or (len(slug) >= 5 and slug[:5] in key):
            return 2
        # realchat ↔ realtimechat style stems
        if seg and (seg.startswith(key[:4]) or key.startswith(seg[:4])):
            return 2
        return 0

    projects = list(data.get("projects") or [])
    # Drop label-only links like "GitHub" / "Official Link|GitHub" so we can replace them.
    for p in projects:
        existing = str(p.get("links") or "")
        if existing and "http://" not in existing.lower() and "https://" not in existing.lower():
            p["links"] = ""

    demo_q = [u for u in rest if "github.com" not in u.lower()]
    gh_q = [u for u in rest if "github.com" in u.lower()]
    assigned_demo: dict[int, str] = {}
    assigned_gh: dict[int, str] = {}

    # Pass 1: name-match URIs to projects
    for i, p in enumerate(projects):
        key = _name_key(str(p.get("name") or ""))
        best_d = max(demo_q, key=lambda u: _uri_score(u, key), default=None)
        if best_d and _uri_score(best_d, key) > 0:
            assigned_demo[i] = best_d
            demo_q.remove(best_d)
        best_g = max(gh_q, key=lambda u: _uri_score(u, key), default=None)
        if best_g and _uri_score(best_g, key) > 0:
            assigned_gh[i] = best_g
            gh_q.remove(best_g)

    # Pass 2: leftovers — demos in order; github prefers projects still missing all links
    di = 0
    for i in range(len(projects)):
        if i not in assigned_demo and di < len(demo_q):
            assigned_demo[i] = demo_q[di]
            di += 1
    gi = 0
    prefer = sorted(
        range(len(projects)),
        key=lambda i: (0 if i not in assigned_demo and i not in assigned_gh else 1, i),
    )
    for i in prefer:
        if i not in assigned_gh and gi < len(gh_q):
            assigned_gh[i] = gh_q[gi]
            gi += 1

    for i, p in enumerate(projects):
        existing = str(p.get("links") or "")
        if "http://" in existing.lower() or "https://" in existing.lower():
            continue
        bundle = [u for u in (assigned_demo.get(i), assigned_gh.get(i)) if u]
        if bundle:
            p["links"] = " | ".join(bundle)
    data["projects"] = projects
    return ResumeExtract(**data)


def extract_resume(path: Path) -> ResumeExtract:
    text = pdf_text(path).strip()
    if len(text) < 80:
        raise ValueError("couldn't read any text from the resume (scanned image PDF?)")
    # Keep as much of the resume as the model can use so custom sections aren't truncated away.
    uris = pdf_uris(path)
    uri_note = ""
    if uris:
        uri_note = "\n\nCLICKABLE LINKS FOUND IN THE PDF (assign to the matching social/portfolio fields):\n" + "\n".join(
            uris[:40]
        )
    ex = ask_json(EXTRACT_SYSTEM, text[:24000] + uri_note, ResumeExtract, temperature=0.0)
    return _apply_pdf_uris(ex, uris)


def _csv(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip() and x.strip() != "-"]


def _flat_skills(ex: ResumeExtract) -> list[str]:
    skills = list(ex.skills or [])
    if skills:
        return skills
    out: list[str] = []
    for c in ex.skill_categories or []:
        out.extend(str(i) for i in (c.items or []) if i)
    return out


def build_profile(ex: ResumeExtract, answers: dict, base: dict) -> dict:
    """Merge extracted resume data + wizard answers over `base` (existing profile or example). Pure, unit-tested."""
    personal_keys = (
        "first_name",
        "last_name",
        "email",
        "phone",
        "location",
        "linkedin",
        "github",
        "website",
        "portfolio",
        "twitter",
    )
    personal = {
        k: clean_contact(answers.get(k) or getattr(ex, k, "") or base.get("personal", {}).get(k, ""), k)
        for k in personal_keys
    }
    # first_name / last_name / phone / location / email are not URL fields — restore uncleaned when clean wiped them
    for k in ("first_name", "last_name", "phone", "location", "email"):
        if not personal.get(k):
            personal[k] = (
                (answers.get(k) or getattr(ex, k, "") or base.get("personal", {}).get(k, "") or "").strip()
            )
            if k == "email" and _PLACEHOLDER_RE.search(personal[k] or ""):
                personal[k] = ""
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

    skills = _flat_skills(ex) or base.get("skills", [])
    skill_categories = (
        [{"name": c.name, "label": c.name, "items": list(c.items)} for c in ex.skill_categories]
        if ex.skill_categories
        else base.get("skill_categories", [])
    )

    out = dict(base)
    out.update(
        personal=personal,
        resume_path=answers.get("resume_path", base.get("resume_path", "./resume.pdf")),
        summary=ex.summary or base.get("summary", ""),
        skills=skills,
        skill_categories=skill_categories,
        experience=[e.model_dump() for e in ex.experience] or base.get("experience", []),
        education=[e.model_dump() for e in ex.education] or base.get("education", []),
        projects=[p.model_dump() for p in ex.projects] if ex.projects else base.get("projects", []),
        honors=list(ex.honors) if ex.honors else base.get("honors", []),
        custom_sections=[c.model_dump() for c in ex.custom_sections]
        if ex.custom_sections
        else base.get("custom_sections", []),
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
            print(
                f"  found {len(ex.experience)} roles, {len(ex.skills)} skills, "
                f"{len(ex.education)} education, {len(ex.projects)} projects, "
                f"{len(ex.honors)} honors, {len(ex.custom_sections)} custom sections"
            )
        except Exception as e:
            print(f"  could not auto-import ({e}); continuing with manual answers")
    elif not rpath.exists():
        print(f"  {rpath} not found. Put your resume there before running `apply` (needed for uploads).")

    bp = base.get("personal", {})
    ans: dict = {"resume_path": str(rpath.relative_to(ROOT)) if rpath.is_relative_to(ROOT) else str(rpath)}
    print("\n-- Contact (check these carefully, they go on every application) --")
    for k, label in [
        ("first_name", "First name"),
        ("last_name", "Last name"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("location", "Location"),
        ("linkedin", "LinkedIn URL"),
        ("github", "GitHub URL"),
        ("website", "Website"),
        ("portfolio", "Portfolio URL"),
        ("twitter", "Twitter / X URL"),
    ]:
        ans[k] = q(label, getattr(ex, k, "") or bp.get(k, ""))
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
    ans["reject_locations"] = _csv(
        q(
            "Reject if location mentions (e.g. roles limited to a country you can't work in)",
            ", ".join(bpref.get("reject_locations", [])) or "US, USA, United States, Canada, UK, Europe",
        )
    )
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
