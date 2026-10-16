"""Enrich agent: fill in missing job descriptions. 3-tier cascade:
JSON-LD JobPosting -> readable page text heuristics -> LLM extraction."""
from __future__ import annotations

import html
import json
import re

import httpx
from pydantic import BaseModel

from ..llm import ask_json
from ..models import Job

UA = {"User-Agent": "Mozilla/5.0 (applyforme job research)"}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def _jsonld(page: str) -> str:
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict) and d.get("@type") == "JobPosting" and d.get("description"):
                return _clean(d["description"])
    return ""


def _page_text(page: str) -> str:
    page = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    m = re.search(r"<(main|article)[^>]*>(.*?)</\1>", page, re.S | re.I)
    return _clean(m.group(2) if m else page)


class _Desc(BaseModel):
    description: str


def enrich(job: Job) -> str:
    """Return a description for the job ('' if unreachable)."""
    r = httpx.get(job.url, headers=UA, timeout=30, follow_redirects=True)
    r.raise_for_status()
    d = _jsonld(r.text)
    if len(d) > 300:
        return d
    text = _page_text(r.text)
    if len(text) < 400:
        return d or text
    # Tier 3: let the LLM pull just the job posting out of a noisy page.
    out = ask_json("Extract the job description (responsibilities, requirements, benefits) from this web page text. Copy faithfully, do not summarize or add anything.", text[:12000], _Desc)
    return out.description or text[:6000]
