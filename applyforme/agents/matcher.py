"""Matcher agent: scores a job against the candidate profile."""
from __future__ import annotations

from ..llm import ask_json
from ..models import Job, MatchResult, Profile
from ..seniority import normalize_level, seniority_ok

SYSTEM = """You are a strict technical recruiter. Score how well the candidate fits the job from 0-100.
Be honest: 90+ only if nearly all hard requirements are met. Penalize missing must-have skills,
seniority mismatch, and location/work-authorization conflicts (e.g. 'Remote' roles restricted to a
country the candidate cannot work in count as a conflict).
SENIORITY: the candidate's target level is given. A junior / entry-level seeker must NOT be scored
highly for Senior / Staff / Principal / Lead / Director roles — put a red flag and keep the score under 40.
Also return `keywords`: 8-15 exact terms from the job description (skills, tools, domains) that the
candidate GENUINELY has according to the profile. Never list a keyword the candidate lacks."""


def match(job: Job, profile: Profile) -> MatchResult:
    level = normalize_level(profile.preferences.seniority_level)
    if not seniority_ok(job.title, level):
        return MatchResult(
            score=15,
            reasons=[f"seniority mismatch: seeking {level}, title looks incompatible"],
            red_flags=[f"blocked for {level} seekers: {job.title}"],
            keywords=[],
        )
    user = (
        f"CANDIDATE TARGET LEVEL: {level}\n"
        f"CURRENT TITLE: {profile.preferences.current_title or '(not set)'}\n"
        f"YEARS EXPERIENCE: {profile.preferences.years_experience if profile.preferences.years_experience is not None else profile.screening.get('years_of_experience', '?')}\n"
        f"TARGET TITLES: {', '.join(profile.preferences.target_titles) or '(any)'}\n\n"
        f"CANDIDATE:\n{profile.model_dump_json(exclude={'screening', 'sources', 'compensation'})}\n\n"
        f"JOB: {job.title} at {job.company} ({job.location})\n{job.description[:6000]}"
    )
    return ask_json(SYSTEM, user, MatchResult)
