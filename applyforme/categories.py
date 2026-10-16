"""Deterministic job categorisation from the title (free, predictable, no LLM tokens)."""
from __future__ import annotations

import re

# Order matters: first match wins, so specific buckets come before generic ones.
RULES: list[tuple[str, str]] = [
    ("Engineering Management", r"\b(engineering manager|head of engineering|director of engineering|vp engineering|tech lead manager)\b"),
    ("Machine Learning / AI", r"\b(machine learning|ml\b|ai\b|applied scientist|research (scientist|engineer)|llm|nlp|computer vision|deep learning)"),
    ("Data", r"\b(data (engineer|scientist|analyst|platform|infrastructure)|analytics|etl|bi\b|business intelligence|database)"),
    ("Security", r"\b(security|appsec|infosec|vulnerability|cryptograph|penetration)"),
    ("DevOps / SRE", r"\b(devops|sre\b|site reliability|platform engineer|infrastructure|cloud engineer|reliability)"),
    ("Mobile", r"\b(ios|android|mobile|swift|kotlin|react native|flutter)"),
    ("QA / Test", r"\b(qa\b|quality assurance|test engineer|sdet|automation engineer)"),
    ("Full-Stack", r"\b(full[- ]?stack)\b"),
    ("Frontend", r"\b(front[- ]?end|ui engineer|web developer|react developer|ux engineer)"),
    ("Backend", r"\b(back[- ]?end|api|server|distributed|systems engineer|software engineer|software developer|developer)"),
    ("Product / Design", r"\b(product (manager|designer)|designer|ux\b|ui/ux)"),
]
OTHER = "Other"
CATEGORIES = [c for c, _ in RULES] + [OTHER]


def categorize(title: str) -> str:
    t = (title or "").lower()
    for name, pat in RULES:
        if re.search(pat, t):
            return name
    return OTHER
