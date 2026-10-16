from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class Preferences(BaseModel):
    target_titles: list[str] = []
    # What the user is aiming for right now: intern | junior | mid | senior | lead | executive
    seniority_level: str = "mid"
    # Current role (used by onboarding / agents to infer stretch vs. mismatch)
    current_title: str = ""
    years_experience: float | None = None
    locations: list[str] = []
    # Jobs whose location mentions any of these are dropped unless an accepted location also matches.
    # Typical use: "Remote" roles that are really "Remote (US only)" are useless from India.
    reject_locations: list[str] = []
    remote_only: bool = False
    min_match_score: int = 70
    exclude_keywords: list[str] = []


class Search(BaseModel):
    """A job-board search (used by the optional JobSpy discovery source)."""

    term: str
    location: str = ""
    sites: list[str] = ["indeed", "google"]  # indeed, linkedin, glassdoor, zip_recruiter, google
    results_wanted: int = 25
    hours_old: int = 72


class Profile(BaseModel):
    searches: list[Search] = []
    personal: dict
    resume_path: str
    summary: str = ""
    skills: list[str] = []
    experience: list[dict] = []
    education: list[dict] = []
    preferences: Preferences = Field(default_factory=Preferences)
    screening: dict = {}
    # Annual salary_expectation / salary_range_min / salary_range_max / salary_currency (used for form answers)
    compensation: dict = {}
    # greenhouse/lever/ashby: list of board slugs; workday: list of {name, base_url, tenant, site_id}
    sources: dict[str, list[Any]] = {}


class Job(BaseModel):
    id: str  # "<ats>:<company>:<native id>"
    ats: str
    company: str
    title: str
    location: str = ""
    url: str  # public job page
    apply_url: str = ""
    description: str = ""


class MatchResult(BaseModel):
    score: int
    reasons: list[str] = []
    red_flags: list[str] = []
    # ATS keywords from the posting that the candidate genuinely has (fed to the resume tailor)
    keywords: list[str] = []


class Tailored(BaseModel):
    cover_letter: str
    why_this_company: str = ""
    resume_highlights: list[str] = []
    resume_pdf: str = ""  # path to the per-job tailored resume (set by the tailor stage)
    resume_tex: str = ""  # LaTeX source of the same resume, ready for Overleaf


class ResumeRole(BaseModel):
    company: str
    title: str
    start: str = ""
    end: str = ""
    bullets: list[str] = []


class ResumeDoc(BaseModel):
    """LLM output for a tailored resume. company/title/dates are validated against the profile."""

    summary: str
    skills: list[str]
    experience: list[ResumeRole]


class FormField(BaseModel):
    key: str  # stable handle we assign (data-afm index)
    label: str
    type: str  # text, textarea, select, checkbox, radio, file, ...
    required: bool = False
    options: list[str] = []


class FieldAnswer(BaseModel):
    key: str
    value: Optional[str] = None  # None => agent doesn't know, ask human
    confidence: float = 0.0
