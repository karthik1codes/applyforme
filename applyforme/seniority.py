"""Seniority / career-level matching: keep junior seekers off senior postings (and vice versa)."""
from __future__ import annotations

import re
from typing import Literal

Level = Literal["intern", "junior", "mid", "senior", "lead", "executive"]

# Ordered from earliest-career to latest. Used to decide which title bands clash.
LEVEL_RANK: dict[str, int] = {
    "intern": 0,
    "junior": 1,
    "mid": 2,
    "senior": 3,
    "lead": 4,
    "executive": 5,
}

# Title tokens that signal a level. Matched as whole words against the job title.
_SIGNALS: list[tuple[str, re.Pattern[str]]] = [
    ("intern", re.compile(r"\b(intern|internship|trainee|apprentice)\b", re.I)),
    ("junior", re.compile(r"\b(junior|jr\.?|entry[- ]level|new[- ]?grad|graduate|associate)\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr\.?)\b", re.I)),
    ("lead", re.compile(r"\b(lead|staff|principal|distinguished|fellow)\b", re.I)),
    ("executive", re.compile(
        r"\b(director|vp|vice[- ]president|head of|chief|cto|ceo|cpo|cfo|founder|partner)\b", re.I
    )),
    ("mid", re.compile(r"\b(mid[- ]?level|intermediate)\b", re.I)),
]

# Extra title fragments always rejected for a given seeker level (even if the posting is ambiguous).
BLOCK_FOR: dict[str, tuple[str, ...]] = {
    "intern": ("senior", "sr.", "staff", "principal", "lead", "director", "manager", "head of", "vp "),
    "junior": (
        "senior", "sr.", "staff", "principal", "lead", "director", "head of", "vp ", "vice president",
        "architect", "manager", "engineering manager",
    ),
    "mid": ("principal", "staff", "distinguished", "director", "vp ", "head of", "intern", "internship"),
    "senior": ("intern", "internship", "junior", "jr.", "entry-level", "entry level", "new grad", "graduate"),
    "lead": ("intern", "internship", "junior", "jr.", "entry-level", "entry level", "new grad"),
    "executive": ("intern", "internship", "junior", "jr.", "entry-level"),
}


def normalize_level(raw: str | None) -> Level:
    s = (raw or "mid").strip().lower()
    aliases = {
        "entry": "junior", "entry-level": "junior", "entry level": "junior", "jr": "junior",
        "new grad": "junior", "graduate": "junior",
        "intermediate": "mid", "middle": "mid",
        "sr": "senior",
        "staff": "lead", "principal": "lead",
        "director": "executive", "manager": "lead", "exec": "executive",
    }
    s = aliases.get(s, s)
    return s if s in LEVEL_RANK else "mid"  # type: ignore[return-value]


def detect_title_level(title: str) -> Level | None:
    """Best-effort level from a job title. None = ambiguous (usually treat as mid)."""
    if not title:
        return None
    for level, pat in _SIGNALS:
        if pat.search(title):
            return level  # type: ignore[return-value]
    return None


def seniority_ok(title: str, seeker_level: str | None) -> bool:
    """False when the posting's seniority clearly clashes with what the user is targeting."""
    seeker = normalize_level(seeker_level)
    low = (title or "").lower()
    for frag in BLOCK_FOR.get(seeker, ()):
        if frag in low:
            return False
    job_level = detect_title_level(title)
    if job_level is None:
        # Ambiguous titles ("Software Engineer") are fine for junior/mid; leads still see them.
        return seeker in ("intern", "junior", "mid", "senior", "lead", "executive")
    gap = LEVEL_RANK[job_level] - LEVEL_RANK[seeker]
    # Allow same level, one step up (stretch), or any step down. Block 2+ levels above.
    if seeker in ("intern", "junior") and job_level in ("senior", "lead", "executive"):
        return False
    if seeker == "mid" and job_level in ("lead", "executive"):
        return False
    if seeker == "senior" and job_level == "executive":
        return gap <= 1  # senior can see some lead; not director/vp via BLOCK_FOR
    return gap <= 1


def default_exclude_for(level: str | None) -> list[str]:
    """Keywords to merge into preferences.exclude_keywords for this seeker level."""
    return {
        "intern": ["senior", "staff", "principal", "lead", "director", "manager"],
        "junior": ["senior", "staff", "principal", "lead", "director", "manager", "architect"],
        "mid": ["intern", "principal", "distinguished", "director", "vp"],
        "senior": ["intern", "junior", "entry-level", "new grad"],
        "lead": ["intern", "junior", "entry-level"],
        "executive": ["intern", "junior"],
    }.get(normalize_level(level), [])
