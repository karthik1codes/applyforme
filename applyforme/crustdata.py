"""Crustdata API client — company enrichment + indexed job search.

Docs: https://docs.crustdata.com/
Auth: Authorization: Bearer $CRUSTDATA_API_KEY
Header: x-api-version: 2025-11-01

Credit model (self-serve, approx):
  /job/search        → 0.03 credits per result
  /company/enrich    → 2 credits per company (base)

This module hard-caps spend so discover/enrich cannot burn hundreds of credits
per run (the previous loop called enrich once per job, often twice).
"""
from __future__ import annotations

import json
import os
import re
import threading
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import DATA_DIR
from .models import Job, Profile

API = "https://api.crustdata.com"
VERSION = "2025-11-01"
TIMEOUT = 45

# Estimated costs used for local budgeting (matches Crustdata pricing docs).
CREDIT_JOB_RESULT = 0.03
CREDIT_COMPANY_ENRICH = 2.0

_CACHE_PATH = DATA_DIR / "crustdata_company_cache.json"
_lock = threading.Lock()
_spent = 0.0
_enrich_count = 0
_cache: dict[str, dict[str, Any]] | None = None


def api_key() -> str:
    return (os.getenv("CRUSTDATA_API_KEY") or "").strip()


def enabled() -> bool:
    return bool(api_key())


def job_search_enabled() -> bool:
    """Indexed job search — optional; JobSpy boards are free. Default off to save credits."""
    return enabled() and os.getenv("CRUSTDATA_JOB_SEARCH", "0").strip().lower() in ("1", "true", "yes", "on")


def max_credits_per_run() -> float:
    try:
        return float(os.getenv("CRUSTDATA_MAX_CREDITS_PER_RUN", "25"))
    except ValueError:
        return 25.0


def max_enrich_per_run() -> int:
    try:
        return max(0, int(os.getenv("CRUSTDATA_MAX_ENRICH_PER_RUN", "5")))
    except ValueError:
        return 5


def job_limit_per_title() -> int:
    try:
        return max(1, min(25, int(os.getenv("CRUSTDATA_JOB_LIMIT_PER_TITLE", "10"))))
    except ValueError:
        return 10


def credits_spent() -> float:
    return _spent


def reset_run_budget() -> None:
    """Call at the start of discover/enrich so each pipeline stage has a fresh budget."""
    global _spent, _enrich_count
    with _lock:
        _spent = 0.0
        _enrich_count = 0


def _budget_ok(need: float) -> bool:
    return (_spent + need) <= max_credits_per_run() + 1e-9


def _charge(amount: float, label: str) -> bool:
    global _spent
    with _lock:
        if (_spent + amount) > max_credits_per_run() + 1e-9:
            print(
                f"[crustdata] budget reached ({_spent:.2f}/{max_credits_per_run():.0f} credits) — skipping {label}"
            )
            return False
        _spent += amount
        return True


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key()}",
        "Content-Type": "application/json",
        "x-api-version": VERSION,
        "Accept": "application/json",
    }


def _post(path: str, body: dict) -> dict[str, Any]:
    if not enabled():
        raise RuntimeError("CRUSTDATA_API_KEY is not set")
    r = httpx.post(f"{API}{path}", headers=_headers(), json=body, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json() if r.content else {}


def _load_cache() -> dict[str, dict[str, Any]]:
    global _cache
    if _cache is not None:
        return _cache
    if _CACHE_PATH.exists():
        try:
            _cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            if not isinstance(_cache, dict):
                _cache = {}
        except Exception:
            _cache = {}
    else:
        _cache = {}
    return _cache


def _save_cache() -> None:
    if _cache is None:
        return
    try:
        _CACHE_PATH.write_text(json.dumps(_cache, indent=0), encoding="utf-8")
    except Exception as e:
        print(f"[crustdata] cache write failed: {e}")


def _cache_key(name: str = "", domain: str = "") -> str:
    d = (domain or "").strip().lower()
    n = (name or "").strip().lower()
    return f"domain:{d}" if d else f"name:{n}"


def careers_url_from_website(website: str | None) -> str:
    """Best-effort careers page from the company website."""
    if not website:
        return ""
    w = website.strip()
    if not w.startswith("http"):
        w = "https://" + w
    base = w.rstrip("/")
    return base + "/careers"


def parse_company_data(company_data: dict) -> dict[str, Any]:
    """Normalize enrich `company_data` into fields we store on Job."""
    basic = company_data.get("basic_info") or {}
    hiring = company_data.get("hiring") or {}
    funding = company_data.get("funding") or {}
    headcount = company_data.get("headcount") or {}
    website = basic.get("website") or ""
    if not website and basic.get("primary_domain"):
        website = f"https://{basic['primary_domain']}"
    openings = hiring.get("recent_openings") or []
    return {
        "crustdata_company_id": basic.get("crustdata_company_id") or company_data.get("crustdata_company_id"),
        "name": basic.get("company_name") or basic.get("name") or "",
        "website": website,
        "careers_url": careers_url_from_website(website),
        "linkedin_url": basic.get("professional_network_url") or "",
        "domain": basic.get("primary_domain") or "",
        "industry": (basic.get("industry") or basic.get("linkedin_industry") or ""),
        "description": basic.get("description") or basic.get("short_description") or "",
        "openings_count": hiring.get("openings_count"),
        "recent_titles": hiring.get("recent_titles_csv") or "",
        "employee_count": headcount.get("linkedin_headcount") or headcount.get("employee_count"),
        "funding_stage": funding.get("last_round_type") or funding.get("stage") or "",
        "recent_openings": [
            {"title": o.get("title"), "url": o.get("url"), "location": o.get("location_text")}
            for o in openings
            if o.get("url") or o.get("title")
        ][:15],
    }


def enrich_company(name: str = "", domain: str = "", linkedin_url: str = "") -> dict[str, Any] | None:
    """Lookup one company. Prefer cache, then domain, then LinkedIn URL, then name.

    Only requests ``basic_info`` (website / LinkedIn) — enough for careers links and
    much cheaper than pulling hiring/funding/headcount/taxonomy every time.
    """
    global _enrich_count
    if not enabled():
        return None

    key = _cache_key(name, domain)
    cache = _load_cache()
    if key in cache:
        return cache[key]
    # Also hit cache by the other key form when both known
    alt = _cache_key(name, "") if domain else ""
    if alt and alt in cache:
        return cache[alt]

    if _enrich_count >= max_enrich_per_run():
        print(f"[crustdata] enrich cap ({max_enrich_per_run()}/run) — skipping {name or domain}")
        return None
    if not _budget_ok(CREDIT_COMPANY_ENRICH):
        print(f"[crustdata] budget would exceed max — skipping enrich for {name or domain}")
        return None

    # Prefer domain (precise) over name (fuzzy / costly retries).
    body: dict[str, Any] = {"fields": ["basic_info"]}
    if domain:
        body["domains"] = [domain.replace("https://", "").replace("http://", "").split("/")[0]]
        body["exact_match"] = True
    elif linkedin_url:
        body["professional_network_profile_urls"] = [linkedin_url]
    elif name:
        body["names"] = [name]
    else:
        return None

    try:
        data = _post("/company/enrich", body)
    except Exception as e:
        print(f"[crustdata] enrich failed for {name or domain}: {e}")
        return None

    if not _charge(CREDIT_COMPANY_ENRICH, f"enrich {name or domain}"):
        return None
    _enrich_count += 1

    results = data if isinstance(data, list) else data.get("results") or data.get("companies") or [data]
    info: dict[str, Any] | None = None
    for item in results:
        matches = item.get("matches") if isinstance(item, dict) else None
        if matches:
            best = max(matches, key=lambda m: m.get("confidence_score") or 0)
            cd = best.get("company_data") or {}
            if cd:
                info = parse_company_data(cd)
                break
        if isinstance(item, dict) and item.get("company_data"):
            info = parse_company_data(item["company_data"])
            break
        if isinstance(item, dict) and item.get("basic_info"):
            info = parse_company_data(item)
            break

    if info:
        cache[key] = info
        if info.get("domain"):
            cache[_cache_key("", info["domain"])] = info
        if info.get("name"):
            cache[_cache_key(info["name"], "")] = info
        _save_cache()
        print(f"[crustdata] enrich ok ({_enrich_count}/{max_enrich_per_run()}, ~{_spent:.2f} credits): {name or domain}")
    return info


def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return re.sub(r"^www\.", "", host)
    except Exception:
        return ""


def _needs_company_enrich(job: Job) -> bool:
    """Skip paid enrich when we already have a usable website / careers link."""
    if job.company_info and (job.company_info.get("website") or job.company_website):
        if job.careers_url or job.company_website:
            return False
    if job.company_website and job.careers_url:
        return False
    return True


def attach_company_info(job: Job) -> Job:
    """Enrich a discovered job with Crustdata company firmographics + careers URL.

    At most one API call (cached). Does not retry domain→name (that doubled credits).
    """
    if not enabled() or not _needs_company_enrich(job):
        if job.company_website and not job.careers_url:
            job.careers_url = careers_url_from_website(job.company_website)
        return job

    domain = ""
    if job.ats in ("greenhouse", "lever", "ashby"):
        domain = _domain_from_url(job.url)
    # Prefer company website domain when we already scraped one from boards
    if not domain and job.company_website:
        domain = _domain_from_url(job.company_website)

    info = enrich_company(name=job.company, domain=domain)
    if not info:
        return job
    job.company_website = info.get("website") or job.company_website
    job.careers_url = info.get("careers_url") or job.careers_url or careers_url_from_website(job.company_website)
    job.company_linkedin = info.get("linkedin_url") or job.company_linkedin
    job.company_info = info
    if not job.apply_url and info.get("recent_openings"):
        for o in info["recent_openings"]:
            if o.get("title") and job.title.lower()[:20] in (o.get("title") or "").lower() and o.get("url"):
                job.apply_url = o["url"]
                break
    return job


def enrich_jobs_budgeted(jobs: list[Job]) -> int:
    """Enrich unique employers missing careers/website, respecting per-run caps.

    Returns number of companies that received a (possibly cached) update.
    Propagates website/careers to other jobs from the same employer.
    """
    if not enabled():
        return 0
    updated = 0
    seen: set[str] = set()
    by_company: dict[str, list[Job]] = {}
    for j in jobs:
        key = (j.company or "").strip().lower()
        if not key:
            continue
        by_company.setdefault(key, []).append(j)

    for key, group in by_company.items():
        if key in seen:
            continue
        seen.add(key)
        # Prefer a job that already has website data as the seed
        seed = next((j for j in group if not _needs_company_enrich(j)), group[0])
        if _needs_company_enrich(seed):
            before = seed.careers_url or seed.company_website
            attach_company_info(seed)
            if (seed.careers_url or seed.company_website) and (seed.careers_url or seed.company_website) != before:
                updated += 1
        # Copy firmographics onto sibling roles at the same company
        for j in group:
            if j is seed:
                continue
            if seed.company_website and not j.company_website:
                j.company_website = seed.company_website
            if seed.careers_url and not j.careers_url:
                j.careers_url = seed.careers_url
            if seed.company_linkedin and not j.company_linkedin:
                j.company_linkedin = seed.company_linkedin
            if seed.company_info and not j.company_info:
                j.company_info = seed.company_info
        if _enrich_count >= max_enrich_per_run() or not _budget_ok(CREDIT_COMPANY_ENRICH):
            left = sum(1 for k, g in by_company.items() if k not in seen and any(_needs_company_enrich(x) for x in g))
            if left:
                print(f"[crustdata] stopped enrich early; ~{left} employers left without paid lookup")
            break
    print(f"[crustdata] company enrich: updated {updated} employers (~{_spent:.2f} credits this run)")
    return updated


def search_jobs(profile: Profile, *, limit_per_title: int | None = None) -> list[Job]:
    """Pull open roles from Crustdata's job index for each target title."""
    if not job_search_enabled():
        if enabled():
            print("[crustdata] job search off (CRUSTDATA_JOB_SEARCH=0) — using free JobSpy boards only")
        else:
            print("[crustdata] CRUSTDATA_API_KEY missing — skipping Crustdata job search")
        return []

    limit = limit_per_title if limit_per_title is not None else job_limit_per_title()
    titles = profile.preferences.target_titles or ["Software Engineer"]
    out: list[Job] = []
    seen: set[str] = set()

    for title in titles:
        # Pre-check budget for a full page of results
        if not _budget_ok(CREDIT_JOB_RESULT * limit):
            print(f"[crustdata] budget too low for another job search — stopping at '{title}'")
            break
        conditions: list[dict] = [
            {"field": "job_details.title", "type": "(.)", "value": title},
        ]
        body = {
            "filters": {"op": "and", "conditions": conditions},
            "fields": [
                "crustdata_job_id",
                "job_details.title",
                "job_details.url",
                "job_details.source",
                "job_details.category",
                "job_details.workplace_type",
                "company.basic_info.name",
                "company.basic_info.website",
                "company.basic_info.primary_domain",
                "company.basic_info.professional_network_url",
                "company.basic_info.crustdata_company_id",
                "location",
                "content",
                "metadata.date_added",
            ],
            "sorts": [{"field": "metadata.date_added", "order": "desc"}],
            "limit": limit,
        }
        try:
            data = _post("/job/search", body)
        except Exception as e:
            print(f"[crustdata] job search '{title}' failed: {e}")
            continue
        listings = data.get("job_listings") or data.get("results") or []
        cost = CREDIT_JOB_RESULT * len(listings)
        if listings and not _charge(cost, f"job search '{title}' ({len(listings)} results)"):
            break
        print(f"[crustdata] job search '{title}': {len(listings)} listings (~{cost:.2f} credits)")
        for row in listings:
            job = job_from_listing(row)
            if not job or job.id in seen:
                continue
            seen.add(job.id)
            out.append(job)
    return out


def job_from_listing(row: dict) -> Job | None:
    details = row.get("job_details") or {}
    company = row.get("company") or {}
    basic = company.get("basic_info") or {}
    loc = row.get("location") or {}
    content = row.get("content") or {}
    url = details.get("url") or ""
    if not url:
        return None
    name = basic.get("company_name") or basic.get("name") or "Unknown"
    website = basic.get("website") or ""
    if not website and basic.get("primary_domain"):
        website = f"https://{basic['primary_domain']}"
    location = (
        loc.get("location_text")
        or ", ".join(x for x in [loc.get("city"), loc.get("region"), loc.get("country")] if x)
        or ""
    )
    cid = row.get("crustdata_job_id") or url
    source = (details.get("source") or "crustdata").lower()
    desc = content.get("description") or content.get("description_text") or ""
    return Job(
        id=f"crustdata:{cid}",
        ats=source if source in ("greenhouse", "lever", "ashby", "workday") else "crustdata",
        company=name,
        title=details.get("title") or "",
        location=location,
        url=url,
        apply_url=url,
        description=desc if isinstance(desc, str) else "",
        company_website=website,
        careers_url=careers_url_from_website(website),
        company_linkedin=basic.get("professional_network_url") or "",
        company_info={
            "crustdata_company_id": basic.get("crustdata_company_id"),
            "website": website,
            "careers_url": careers_url_from_website(website),
            "linkedin_url": basic.get("professional_network_url") or "",
            "domain": basic.get("primary_domain") or "",
        },
    )
