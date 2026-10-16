"""Output hygiene for LLM-written text: sanitising, leak detection and cover-letter checks.

Cheap, deterministic guards that run before anything is saved or sent to an employer.
"""
from __future__ import annotations

import re

# Phrases that mean the model talked to *us* instead of writing the document.
LEAK_PHRASES = [
    "as an ai", "language model", "i cannot", "i can't assist", "i'm sorry", "i apologize",
    "here is the", "here's the", "here is your", "certainly!", "sure!", "of course!",
    "note:", "as requested", "i have tailored", "i've tailored", "[insert", "lorem ipsum",
]

# Overused filler that makes a letter read as machine-written. Warning only, never blocking.
CLICHES = [
    "passionate", "leverage", "synergy", "spearheaded", "thrilled", "excited to apply",
    "dynamic", "cutting-edge", "results-driven", "go-getter", "think outside the box",
    "proven track record", "rockstar", "ninja", "game-changer", "delve", "tapestry",
    "i am writing to apply", "i am writing to express",
]

_PLACEHOLDER = re.compile(r"\[[A-Za-z][A-Za-z '\-/]{2,40}\]|\{\{[^}]+\}\}|<[A-Z][A-Za-z ]{2,30}>")

MAX_COVER_WORDS = 260
MIN_COVER_WORDS = 60


def sanitize_text(text: str) -> str:
    """Normalise typographic characters that look machine-generated or break PDF/LaTeX fonts."""
    if not text:
        return text
    t = text.replace("\u2014", ", ").replace("\u2013", "-").replace("\u2212", "-")
    t = t.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    t = t.replace("\u2026", "...").replace("\u00a0", " ").replace("\u200b", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" ,", ",", t)
    t = re.sub(r",\s*,", ",", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def find_leaks(text: str) -> list[str]:
    low = text.lower()
    return [p for p in LEAK_PHRASES if p in low]


def find_cliches(text: str) -> list[str]:
    low = text.lower()
    return [c for c in CLICHES if c in low]


def validate_cover_letter(text: str, *, candidate_name: str = "") -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors force a regeneration; warnings are just surfaced."""
    errors: list[str] = []
    warnings: list[str] = []
    words = len(text.split())
    if words > MAX_COVER_WORDS:
        errors.append(f"too long ({words} words, max {MAX_COVER_WORDS})")
    if words < MIN_COVER_WORDS:
        errors.append(f"too short ({words} words, min {MIN_COVER_WORDS})")
    if leaks := find_leaks(text):
        errors.append(f"contains assistant-style phrasing: {', '.join(leaks)}")
    if _PLACEHOLDER.search(text):
        errors.append("contains an unfilled placeholder like [Company Name]")
    if candidate_name and candidate_name.split()[0].lower() not in text.lower()[-200:]:
        warnings.append("does not appear to be signed with the candidate's name")
    if cl := find_cliches(text):
        warnings.append(f"cliches: {', '.join(cl)}")
    return errors, warnings
