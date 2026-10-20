from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class Preferences(BaseModel):
    target_titles: list[str] = []
    # What the user is aiming for right now: intern | junior | mid | senior | lead | executive
    seniority_level: str = "mid"
    # What to pull: jobs | internships | both  (set in onboarding)
    search_focus: str = "jobs"
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

    def wants_jobs(self) -> bool:
        return (self.search_focus or "jobs").lower() in ("jobs", "both", "fulltime", "full-time", "")

    def wants_internships(self) -> bool:
        return (self.search_focus or "jobs").lower() in ("internships", "internship", "both", "intern")


DEFAULT_BOARD_SITES = ["indeed", "linkedin", "glassdoor", "zip_recruiter", "google"]


class Search(BaseModel):
    """Job-board search — always run by discovery via JobSpy (Indeed/LinkedIn/Glassdoor/ZipRecruiter/Google)."""

    term: str
    location: str = ""
    sites: list[str] = Field(default_factory=lambda: list(DEFAULT_BOARD_SITES))
    results_wanted: int = 25
    hours_old: int = 72


class Profile(BaseModel):
    # If empty at discover time, searches are built from preferences.target_titles + locations.
    searches: list[Search] = Field(default_factory=list)
    personal: dict
    resume_path: str
    summary: str = ""
    skills: list[str] = []
    skill_categories: list[dict] = Field(default_factory=list)
    experience: list[dict] = []
    education: list[dict] = []
    projects: list[dict] = Field(default_factory=list)
    honors: list[str] = Field(default_factory=list)
    custom_sections: list[dict] = Field(default_factory=list)
    # Editor prefs: show_summary, portfolio_label
    resume: dict = Field(default_factory=dict)
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
    url: str  # public job / posting page (shown to the user)
    apply_url: str = ""
    description: str = ""
    # Filled by Crustdata company enrich / job search
    company_website: str = ""
    careers_url: str = ""  # company careers page (best-effort)
    company_linkedin: str = ""
    company_info: dict = Field(default_factory=dict)

    def target_url(self) -> str:
        """URL the applier should open.

        Keep LinkedIn postings on LinkedIn so the agent can use Easy Apply; an
        ``apply_url`` from the board often points at the employer ATS and would
        skip LinkedIn entirely. Non-LinkedIn jobs still prefer the direct ATS URL.
        """
        url = (self.url or "").strip()
        if "linkedin.com" in url.lower():
            return url
        return (self.apply_url or url).strip()


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
    location: str = ""
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
    type: str  # text, textarea, select, checkbox, radio, file, custom_select, ...
    required: bool = False
    options: list[str] = []
    name: str = ""
    element_id: str = ""
    placeholder: str = ""
    current: str = ""  # value already present in the control
    checked: bool = False
    frame_index: int = 0  # 0 = main frame; >0 = iframe in page.frames order


class FieldAnswer(BaseModel):
    key: str
    value: Optional[str] = None  # None => agent doesn't know, ask human
    confidence: float = 0.0
    source: str = "llm"  # profile | llm | human
