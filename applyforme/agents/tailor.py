"""Tailor agent: writes a grounded cover letter. Never invents experience."""
from __future__ import annotations

from ..llm import ask_json
from ..models import Job, Profile, Tailored
from ..quality import CLICHES, sanitize_text, validate_cover_letter

SYSTEM = f"""You write concise, specific cover letters (120-220 words, no 'I am writing to apply').
HARD RULES:
- Use ONLY facts present in the candidate profile. Never invent employers, metrics, skills, or degrees.
- Connect 2-3 real accomplishments to the job's actual needs. If ATS keywords are supplied, work in the ones
  that are genuinely true of the candidate, naturally, never as a list.
- Plain, confident, human tone. Avoid filler such as: {', '.join(CLICHES[:12])}.
- Do not use em dashes. No placeholders like [Company]. Output only the letter itself, no commentary.
- Sign off with the candidate's first and last name."""

ATTEMPTS = 3


def tailor(job: Job, profile: Profile, keywords: list[str] | None = None) -> Tailored:
    base = (
        f"CANDIDATE:\n{profile.model_dump_json(exclude={'screening', 'sources', 'compensation'})}\n\n"
        f"JOB: {job.title} at {job.company}\n{job.description[:6000]}"
    )
    if keywords:
        base += f"\n\nATS KEYWORDS (use only where truthful): {', '.join(keywords[:15])}"
    p = profile.personal
    name = str(p.get("name") or p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}").strip()
    problems: list[str] = []
    last: Tailored | None = None
    for attempt in range(ATTEMPTS):
        # Every attempt is a fresh conversation (no earlier draft in context), so the model can't spiral into apologies.
        user = base
        if problems:
            user += "\n\nA previous draft was rejected because it was " + "; ".join(problems) + ". Write a corrected letter."
        t = ask_json(SYSTEM, user, Tailored, temperature=0.5 + 0.15 * attempt)
        t.cover_letter = sanitize_text(t.cover_letter)
        t.why_this_company = sanitize_text(t.why_this_company)
        t.resume_highlights = [sanitize_text(h) for h in t.resume_highlights]
        errors, warnings = validate_cover_letter(t.cover_letter, candidate_name=name)
        if not errors:
            for w in warnings:
                print(f"    note: cover letter {w}")
            return t
        problems, last = errors, t
    raise RuntimeError(f"cover letter failed checks after {ATTEMPTS} attempts: {'; '.join(problems)}")
