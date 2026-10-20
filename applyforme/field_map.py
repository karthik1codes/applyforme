"""Deterministic profile -> application-form field mapping.

The LLM is good at unusual free-text questions, but it is the wrong tool for
``First name`` or ``Email``: it is slower, non-deterministic, and can invent a
value.  This module maps the common fields from the candidate's saved profile
before any model call.  Anything it cannot verify is left unknown so the
applier can ask the human instead of guessing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import FieldAnswer, FormField, Profile, Tailored


def norm(text: str) -> str:
    """Lowercase, strip required markers and collapse punctuation."""
    s = (text or "").lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[\*\(\)\[\]\{\}:;,.!?/\\|_\-]+", " ", s)
    s = re.sub(r"\b(required|optional|mandatory)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def split_name(full: str) -> tuple[str, str]:
    parts = [p for p in re.split(r"\s+", (full or "").strip()) if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


@dataclass
class Candidate:
    values: dict[str, str | None]
    options: dict[str, list[str]]

    def get(self, key: str) -> str | None:
        v = self.values.get(key)
        return v if v not in (None, "") else None


def candidate_from_profile(profile: Profile, tailored: Tailored | None = None) -> Candidate:
    personal = profile.personal or {}
    first = str(personal.get("first_name") or "").strip()
    last = str(personal.get("last_name") or "").strip()
    full = str(personal.get("name") or personal.get("full_name") or "").strip()
    if not (first or last) and full:
        first, last = split_name(full)
    if not full:
        full = " ".join(x for x in (first, last) if x).strip()

    screening = {norm(str(k)): str(v) for k, v in (profile.screening or {}).items() if v not in (None, "")}
    comp = profile.compensation or {}
    prefs = profile.preferences
    experience = profile.experience or []
    current = experience[0] if experience and isinstance(experience[0], dict) else {}
    education = profile.education or []
    edu = education[0] if education and isinstance(education[0], dict) else {}

    def screen(*keys: str) -> str | None:
        for k in keys:
            v = screening.get(norm(k))
            if v:
                return v
        return None

    locations = [str(x).strip() for x in (prefs.locations or []) if str(x).strip()]
    # The user explicitly listed accepted locations during onboarding.  It is
    # still user-provided data, but a location field should not be invented from
    # a scraped job ad.
    location = str(personal.get("location") or personal.get("city") or "").strip()
    if not location and locations:
        location = locations[0]
    city = str(personal.get("city") or "").strip()
    if not city and location and "," in location:
        city = location.split(",", 1)[0].strip()

    salary = str(
        comp.get("salary_expectation")
        or screening.get("expected salary")
        or screen("expected_salary", "expected salary", "desired salary")
        or ""
    ).strip()

    values: dict[str, str | None] = {
        "first_name": first or None,
        "last_name": last or None,
        "full_name": full or None,
        "email": str(personal.get("email") or "").strip() or None,
        "phone": str(personal.get("phone") or personal.get("mobile") or "").strip() or None,
        "city": city or None,
        "location": location or None,
        "country": str(personal.get("country") or "").strip() or None,
        "linkedin_url": str(personal.get("linkedin") or personal.get("linkedin_url") or "").strip() or None,
        "github_url": str(personal.get("github") or personal.get("github_url") or "").strip() or None,
        "portfolio_url": str(personal.get("portfolio") or "").strip() or None,
        "website_url": str(personal.get("website") or personal.get("portfolio") or "").strip() or None,
        "twitter_url": str(personal.get("twitter") or personal.get("x") or "").strip() or None,
        "resume": "RESUME" if profile.resume_path else None,
        "cover_letter": (tailored.cover_letter if tailored and tailored.cover_letter else None),
        "work_authorization": screen("work_authorization", "work authorization", "authorized to work"),
        "requires_sponsorship": screen("requires_sponsorship", "requires sponsorship", "sponsorship"),
        "notice_period": screen("notice_period", "notice period", "availability"),
        "expected_salary": salary or None,
        "years_of_experience": screen("years_of_experience", "years of experience")
        or (str(prefs.years_experience) if prefs.years_experience is not None else None),
        "gender": screen("gender"),
        "veteran_status": screen("veteran_status", "veteran status"),
        "disability_status": screen("disability_status", "disability status"),
        "race_ethnicity": screen("race_ethnicity", "race", "ethnicity"),
        "how_did_you_hear": screen("how_did_you_hear", "how did you hear")
        or str((getattr(profile, "attribution", None) or {}).get("how_heard") or "").strip()
        or None,
        "current_company": str(current.get("company") or "").strip() or None,
        "current_title": str(current.get("title") or prefs.current_title or "").strip() or None,
        "education_school": str(edu.get("school") or edu.get("institution") or "").strip() or None,
        "education_degree": str(edu.get("degree") or "").strip() or None,
        "education_field": str(edu.get("field") or edu.get("field_of_study") or "").strip() or None,
        "education_year": str(edu.get("year") or edu.get("graduation_year") or "").strip() or None,
        "18_or_older": screen("18_or_older", "18 years or older", "at least 18"),
        "background_check": screen("background_check", "background check"),
        "previously_employed": screen("previously_employed", "previously employed"),
    }
    return Candidate(values=values, options={})


# Order matters: more specific labels first.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("first_name", re.compile(r"\b(first|given|forename)\s*name\b|\bfname\b|\bgiven\b")),
    ("last_name", re.compile(r"\b(last|family|sur)\s*name\b|\blname\b|\bsurname\b")),
    ("full_name", re.compile(r"\b(full|legal|your)\s*name\b|^name$|\bname of applicant\b")),
    ("email", re.compile(r"\b(e[\s-]?mail)(\s*address)?\b")),
    ("phone", re.compile(r"\b(phone|mobile|telephone|contact number|cell)\b")),
    ("linkedin_url", re.compile(r"\blinked\s*in\b|\blinkedin\b")),
    ("github_url", re.compile(r"\bgit\s*hub\b|\bgithub\b")),
    ("portfolio_url", re.compile(r"\bportfolio\b|\bpersonal site\b|\bpersonal website\b")),
    ("website_url", re.compile(r"\bwebsite\b|\bweb site\b|\burl\b")),
    ("twitter_url", re.compile(r"\btwitter\b|\bx \(formerly twitter\)\b|\bx profile\b")),
    ("city", re.compile(r"\bcity\b|\btown\b|\bcity of residence\b")),
    ("location", re.compile(r"\blocation\b|\bwhere are you (based|located)\b|\bcurrent location\b")),
    ("country", re.compile(r"\bcountry\b")),
    ("resume", re.compile(r"\bresume\b|\bcv\b|\bcurriculum vitae\b")),
    ("cover_letter", re.compile(r"\bcover letter\b|\bcoverletter\b")),
    ("work_authorization", re.compile(
        r"\b(legally\s+)?authori[sz]ed to work\b|\bright to work\b|\bwork authori[sz]ation\b|\beligible to work\b"
    )),
    ("requires_sponsorship", re.compile(r"\bsponsor(ship)?\b|\bvisa\b")),
    ("notice_period", re.compile(r"\bnotice period\b|\bavailability to start\b|\bwhen can you start\b")),
    ("expected_salary", re.compile(
        r"\b(expected|desired|target)\s+(salary|compensation|pay|ctc)\b|\bsalary (expectation|requirement)\b|\bcompensation\b"
    )),
    ("years_of_experience", re.compile(r"\b(years?|yrs?)\s+(of\s+)?experience\b|\btotal experience\b")),
    ("gender", re.compile(r"\bgender\b|\bsex\b")),
    ("veteran_status", re.compile(r"\bveteran\b")),
    ("disability_status", re.compile(r"\bdisabilit(y|ies)\b")),
    ("race_ethnicity", re.compile(r"\brace\b|\bethnicity\b|\bethnic\b")),
    ("how_did_you_hear", re.compile(r"\bhow did you hear\b|\bhow did you find\b|\breferral source\b|\bsource\b")),
    ("current_company", re.compile(r"\b(current|present)\s+(company|employer)\b|\bcurrent employer\b")),
    ("current_title", re.compile(r"\b(current|present)\s+(job\s+)?title\b|\bcurrent role\b|\bjob title\b")),
    ("education_school", re.compile(r"\b(school|university|college|institution)\b")),
    ("education_degree", re.compile(r"\bdegree\b|\bqualification\b")),
    ("education_field", re.compile(r"\bfield of study\b|\bmajor\b|\bspeciali[sz]ation\b")),
    ("education_year", re.compile(r"\b(graduation|graduate|passing)\s*(year|date)\b|\byear of graduation\b")),
    ("18_or_older", re.compile(r"\b(18|eighteen)\s*(years?)?\s*(or older|of age)\b|\bat least 18\b")),
    ("background_check", re.compile(r"\bbackground check\b|\bcriminal (record|history)\b")),
    ("previously_employed", re.compile(r"\bpreviously (employed|worked)\b|\bworked (here|for us) before\b")),
]

_CONSENT = re.compile(
    r"\b(i agree|agree to|consent|terms|privacy|acknowledge|confirm that|certify|accurate)\b"
)
_COVER_LETTER_TEXT = re.compile(r"\bcover letter\b|\bwhy (do )?you want\b|\bwhy this (company|role)\b")

_DECLINE = ("decline", "prefer not", "don't wish", "do not wish", "not to disclose", "no answer", "n/a")
_AFFIRM = ("yes", "i agree", "agree", "accept", "acknowledge", "confirm", "consent", "true")


def _choose_option(value: str | None, options: list[str], *, kind: str = "") -> str | None:
    """Return the option label that best represents ``value`` (or None)."""
    opts = [str(o).strip() for o in options if str(o).strip()]
    if not opts:
        return value
    if value in (None, ""):
        return None
    v = norm(value)
    normed = [(o, norm(o)) for o in opts]

    # Exact / substring first.
    for o, no in normed:
        if no == v:
            return o
    for o, no in normed:
        if v and (v in no or no in v):
            return o

    # Numeric values often carry separators/currency in option labels.
    vdigits = re.sub(r"[^0-9]", "", value)
    if vdigits:
        for o in opts:
            if re.sub(r"[^0-9]", "", o) == vdigits:
                return o

    # Yes/no style questions: the profile may store a sentence.
    if v.startswith("yes") or v in ("true", "authorized", "eligible"):
        for o, no in normed:
            if no == "yes" or no.startswith("yes"):
                return o
    if v.startswith("no") or v in ("false", "not authorized"):
        for o, no in normed:
            if no == "no" or no.startswith("no"):
                return o

    if kind in ("gender", "veteran_status", "disability_status", "race_ethnicity"):
        for o, no in normed:
            if any(d in no for d in _DECLINE):
                return o
    return None


def _affirmative_option(options: list[str]) -> str | None:
    for o in options:
        if any(a in norm(o) for a in _AFFIRM):
            return o
    return options[0] if len(options) == 1 else None


def _decline_option(options: list[str]) -> str | None:
    for o in options:
        if any(d in norm(o) for d in _DECLINE):
            return o
    return None


def _haystack(f: FormField) -> str:
    # A field's visible label is the strongest signal; name/id/placeholder help
    # when a designer used an icon-only label.
    return norm(" ".join(x for x in (f.label, f.name, f.element_id, f.placeholder) if x))


def map_field(f: FormField, cand: Candidate) -> FieldAnswer | None:
    """Map one form field deterministically, or return None when unsure."""
    hay = _haystack(f)

    # File inputs are special: only the resume / cover letter are known files.
    if f.type == "file":
        if "cover" in hay:
            return FieldAnswer(key=f.key, value=cand.get("cover_letter") and "COVER_LETTER", confidence=0.9, source="profile")
        if "resume" in hay or "cv" in hay or not hay:
            return FieldAnswer(key=f.key, value="RESUME", confidence=0.95, source="profile")
        return None

    # Cover-letter textareas use the tailored letter, not a URL.
    if f.type == "textarea" and _COVER_LETTER_TEXT.search(hay):
        v = cand.get("cover_letter")
        return FieldAnswer(key=f.key, value=v, confidence=0.9, source="profile") if v else None

    # Consent / terms checkboxes: choose an affirmative option if one exists.
    if _CONSENT.search(hay) and f.type in ("checkbox", "radio"):
        v = _affirmative_option(f.options)
        if v:
            return FieldAnswer(key=f.key, value=v, confidence=0.9, source="profile")

    for key, pattern in _PATTERNS:
        if not pattern.search(hay):
            continue
        # Avoid mapping "company website" to the candidate's personal website.
        if key in ("website_url", "portfolio_url") and re.search(r"\b(company|employer|organization)\b", hay):
            continue
        value = cand.get(key)
        if value is None:
            # Demographic questions with no saved answer get an explicit
            # decline option when one exists; never a guessed demographic.
            if key in ("gender", "veteran_status", "disability_status", "race_ethnicity"):
                decline = _decline_option(f.options)
                if decline:
                    return FieldAnswer(key=f.key, value=decline, confidence=0.8, source="profile")
            return None
        if f.options:
            chosen = _choose_option(value, f.options, kind=key)
            if chosen is None:
                # Don't send an invalid option; leave it for the human.
                if key in ("gender", "veteran_status", "disability_status", "race_ethnicity"):
                    chosen = _decline_option(f.options)
                if chosen is None:
                    return None
            value = chosen
        return FieldAnswer(key=f.key, value=str(value), confidence=0.95, source="profile")
    return None


def map_fields(fields: list[FormField], profile: Profile, tailored: Tailored | None = None) -> dict[str, FieldAnswer]:
    cand = candidate_from_profile(profile, tailored)
    out: dict[str, FieldAnswer] = {}
    for f in fields:
        answer = map_field(f, cand)
        if answer is not None and answer.value not in (None, ""):
            out[f.key] = answer
    return out


def unknown_required(fields: list[FormField], answers: dict[str, FieldAnswer]) -> list[FormField]:
    return [f for f in fields if f.key not in answers and _is_required(f)]


def _is_required(f: FormField) -> bool:
    return bool(f.required) or "*" in (f.label or "") or "required" in (f.label or "").lower()
