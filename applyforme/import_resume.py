"""Non-interactive resume import: PDF/TXT → profile.yaml (full sections + contact).

Used after dashboard upload so Tailor can build per-job PDFs from the real resume
and the Profile form is auto-filled without manual entry.
`python -m applyforme import-resume [--path resume.pdf]`
"""
from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from .config import ROOT
from .wizard import _flat_skills, build_profile, clean_contact, extract_resume


def import_resume_file(path: str | Path | None = None) -> dict:
    """Extract structured data from the uploaded resume and merge into profile.yaml.

    Preserves preferences / screening / compensation. Overwrites personal contact,
    summary, skills, experience, education, projects, honors, and custom sections
    from the resume whenever the extract has values (so Profile auto-fills on upload).
    """
    target = ROOT / "profile.yaml"
    src = target if target.exists() else ROOT / "profile.example.yaml"
    base = yaml.safe_load(src.read_text(encoding="utf-8")) or {}

    rpath = Path(path) if path else Path(base.get("resume_path") or "./resume.pdf")
    if not rpath.is_absolute():
        rpath = (ROOT / rpath).resolve()
    if not rpath.exists():
        for name in ("resume.pdf", "resume.txt"):
            cand = ROOT / name
            if cand.exists():
                rpath = cand
                break
    if not rpath.exists():
        raise FileNotFoundError(f"Resume not found at {rpath}")

    print(f"[import-resume] reading {rpath}")
    ex = extract_resume(rpath)
    print(
        f"[import-resume] extracted {len(ex.experience)} roles, "
        f"{len(_flat_skills(ex))} skills, {len(ex.education)} education, "
        f"{len(ex.projects)} projects, {len(ex.honors)} honors, "
        f"{len(ex.custom_sections)} custom sections"
    )

    bp = base.get("personal") or {}
    # Resume wins for contact/socials so Profile fields fill automatically on upload.
    # Drop placeholder / label-only values from both extract and previous profile.
    ans: dict = {
        "resume_path": "./resume.pdf" if (ROOT / "resume.pdf").exists() else str(rpath),
    }
    for k in (
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
    ):
        from_ex = clean_contact(getattr(ex, k, "") or "", k)
        from_base = clean_contact(bp.get(k) or "", k)
        ans[k] = from_ex or from_base or ""

    bs, bc = base.get("screening") or {}, base.get("compensation") or {}
    ans["salary_currency"] = bc.get("salary_currency", "INR")
    ans["salary_expectation"] = str(bc.get("salary_expectation", "") or "")
    ans["salary_range_min"] = str(bc.get("salary_range_min", "") or ans["salary_expectation"])
    ans["salary_range_max"] = str(bc.get("salary_range_max", "") or ans["salary_expectation"])
    ans["work_authorization"] = bs.get("work_authorization", "")
    ans["requires_sponsorship"] = bs.get("requires_sponsorship", "No")
    ans["notice_period"] = bs.get("notice_period", "")
    ans["years_of_experience"] = str(bs.get("years_of_experience", "") or "")

    prof = build_profile(ex, ans, base)

    # Force resume sections even when lists were empty in base / merge edge cases.
    if ex.experience:
        prof["experience"] = [e.model_dump() for e in ex.experience]
    skills = _flat_skills(ex)
    if skills:
        prof["skills"] = skills
    if ex.skill_categories:
        prof["skill_categories"] = [
            {"name": c.name, "label": c.name, "items": list(c.items)} for c in ex.skill_categories
        ]
    if ex.education:
        prof["education"] = [e.model_dump() for e in ex.education]
    # Only keep a summary that was on the resume — never invent one.
    prof["summary"] = (ex.summary or "").strip()
    if ex.projects:
        prof["projects"] = [p.model_dump() for p in ex.projects]
    if ex.honors:
        prof["honors"] = list(ex.honors)
    if ex.custom_sections:
        prof["custom_sections"] = [c.model_dump() for c in ex.custom_sections]

    personal = dict(prof.get("personal") or {})
    for k in (
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
    ):
        personal[k] = ans.get(k) or clean_contact(personal.get(k) or "", k)
    prof["personal"] = personal

    if target.exists():
        shutil.copy(target, target.with_suffix(".yaml.bak"))
    header = (
        "# Updated by resume import (dashboard upload / `import-resume`). "
        "Tailor uses this for per-job PDFs. Contact + sections filled from the PDF.\n"
    )
    target.write_text(header + yaml.safe_dump(prof, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"[import-resume] wrote {target}")
    return {
        "path": str(rpath),
        "roles": len(ex.experience),
        "skills": len(skills or prof.get("skills") or []),
        "education": len(ex.education),
        "projects": len(ex.projects),
        "honors": len(ex.honors),
        "custom_sections": len(ex.custom_sections),
        "name": f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip(),
        "email": personal.get("email", ""),
    }
