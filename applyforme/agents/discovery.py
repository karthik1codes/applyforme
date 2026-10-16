"""Discovery agent: pulls open roles from public ATS job-board APIs (no scraping/login)."""
from __future__ import annotations

import re

import httpx

from ..models import Job, Profile

TIMEOUT = 30


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def greenhouse(board: str) -> list[Job]:
    r = httpx.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", params={"content": "true"}, timeout=TIMEOUT)
    r.raise_for_status()
    return [
        Job(
            id=f"greenhouse:{board}:{j['id']}",
            ats="greenhouse",
            company=board,
            title=j["title"],
            location=(j.get("location") or {}).get("name", ""),
            url=j["absolute_url"],
            apply_url=j["absolute_url"],
            description=_strip_html(__import__("html").unescape(j.get("content", ""))),
        )
        for j in r.json().get("jobs", [])
    ]


def lever(company: str) -> list[Job]:
    r = httpx.get(f"https://api.lever.co/v0/postings/{company}", params={"mode": "json"}, timeout=TIMEOUT)
    r.raise_for_status()
    return [
        Job(
            id=f"lever:{company}:{j['id']}",
            ats="lever",
            company=company,
            title=j["text"],
            location=(j.get("categories") or {}).get("location", "") or "",
            url=j["hostedUrl"],
            apply_url=j.get("applyUrl", j["hostedUrl"]),
            description=j.get("descriptionPlain", ""),
        )
        for j in r.json()
    ]


def ashby(company: str) -> list[Job]:
    r = httpx.get(f"https://api.ashbyhq.com/posting-api/job-board/{company}", timeout=TIMEOUT)
    r.raise_for_status()
    return [
        Job(
            id=f"ashby:{company}:{j['id']}",
            ats="ashby",
            company=company,
            title=j["title"],
            location=j.get("location", "") or "",
            url=j["jobUrl"],
            apply_url=j.get("applyUrl", j["jobUrl"]),
            description=j.get("descriptionPlain", ""),
        )
        for j in r.json().get("jobs", [])
        if j.get("isListed", True)
    ]


_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "application/json"}


def workday_search(emp: dict, query: str, offset: int = 0, limit: int = 20) -> dict:
    """Workday career sites expose a public JSON search endpoint (the same one their own page calls)."""
    api = f"{emp['base_url'].rstrip('/')}/wday/cxs/{emp['tenant']}/{emp['site_id']}/jobs"
    r = httpx.post(api, json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": query},
                   headers=_UA, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def workday_description(emp: dict, external_path: str) -> str:
    api = f"{emp['base_url'].rstrip('/')}/wday/cxs/{emp['tenant']}/{emp['site_id']}{external_path}"
    r = httpx.get(api, headers=_UA, timeout=TIMEOUT)
    r.raise_for_status()
    info = r.json().get("jobPostingInfo", {})
    return _strip_html(__import__("html").unescape(info.get("jobDescription", "")))


def workday(emp: dict, queries: list[str] | None = None, max_per_query: int = 60) -> list[Job]:
    """List jobs for one Workday employer. Descriptions are filled in later (only for jobs that pass the filter)."""
    found: dict[str, dict] = {}
    for q in queries or [""]:
        offset = 0
        while offset < max_per_query:
            data = workday_search(emp, q, offset)
            posts = data.get("jobPostings") or []
            for p in posts:
                if p.get("externalPath"):
                    found.setdefault(p["externalPath"], p)
            offset += 20
            if not posts or offset >= data.get("total", 0):
                break
    base, site, tenant = emp["base_url"].rstrip("/"), emp["site_id"], emp["tenant"]
    return [
        Job(
            id=f"workday:{tenant}:{path.rsplit('/', 1)[-1]}",
            ats="workday",
            company=emp.get("name", tenant),
            title=p.get("title", ""),
            location=p.get("locationsText", "") or "",
            url=f"{base}/en-US/{site}{path}",
            apply_url=f"{base}/en-US/{site}{path}",
        )
        for path, p in found.items()
    ]


def fill_workday_description(emp: dict, job: Job) -> None:
    path = job.url.split(f"/{emp['site_id']}", 1)[-1]
    try:
        job.description = workday_description(emp, path)
    except Exception as e:
        print(f"[discovery] workday description failed for {job.title}: {e}")


FETCHERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}

_REMOTE = re.compile(r"\b(remote|anywhere|work from home|wfh|distributed|worldwide)\b")


def _has_any(tokens: list[str], text: str) -> bool:
    return any(re.search(rf"(?<![a-z0-9]){re.escape(t.lower())}(?![a-z0-9])", text) for t in tokens if t.strip())


def location_ok(location: str, prefs) -> bool:
    """Accept/reject logic. A bare 'Remote' is fine, but 'Remote (US only)' is not when 'US' is in reject_locations."""
    loc = (location or "").lower()
    if not loc.strip():
        return not prefs.locations  # unknown location: only let it through if the user has no location preference
    if re.fullmatch(r"\s*\d+\s+locations?\s*", loc):
        return True  # Workday collapses multi-location roles to "2 Locations"; let the scorer decide from the description
    remote = bool(_REMOTE.search(loc))
    if prefs.remote_only and not remote:
        return False
    places = [l for l in prefs.locations if l.strip().lower() != "remote"]
    wants_remote = not prefs.locations or any(l.strip().lower() == "remote" for l in prefs.locations)
    if places and _has_any(places, loc):
        return True  # explicitly in a place we want
    if prefs.reject_locations and _has_any(prefs.reject_locations, loc):
        return False
    if remote and wants_remote:
        return True
    return not prefs.locations


def prefilter(job: Job, profile: Profile) -> bool:
    """Cheap, free keyword filter before spending LLM tokens."""
    from ..seniority import default_exclude_for, seniority_ok

    p = profile.preferences
    title = job.title.lower()
    blocked = {k.lower() for k in p.exclude_keywords} | {k.lower() for k in default_exclude_for(p.seniority_level)}
    if any(k in title for k in blocked if k):
        return False
    if not seniority_ok(job.title, p.seniority_level):
        return False
    if p.target_titles and not any(
        all(w in title for w in t.lower().split()) or t.lower() in title for t in p.target_titles
    ):
        return False
    return location_ok(f"{job.location} {'remote' if 'remote' in title else ''}", p)


AGGREGATORS = {"indeed", "linkedin", "glassdoor", "zip_recruiter", "google"}


def jobboards(profile: Profile) -> list[Job]:
    """Optional: search Indeed/LinkedIn/Glassdoor/ZipRecruiter/Google via python-jobspy.
    NOTE: these sites' terms restrict automated scraping (LinkedIn especially). Use sparingly, at your own risk."""
    if not profile.searches:
        return []
    try:
        from jobspy import scrape_jobs
    except ImportError:
        print("[discovery] searches configured but python-jobspy not installed: pip install python-jobspy")
        return []
    out: list[Job] = []
    for s in profile.searches:
        try:
            df = scrape_jobs(site_name=s.sites, search_term=s.term, location=s.location,
                             results_wanted=s.results_wanted, hours_old=s.hours_old)
        except Exception as e:
            print(f"[discovery] jobspy '{s.term}' failed: {e}")
            continue
        for r in df.to_dict("records"):
            url = str(r.get("job_url") or "")
            if not url:
                continue
            direct = str(r.get("job_url_direct") or "")
            out.append(Job(
                id=f"{r.get('site')}:{r.get('id') or url}",
                ats=str(r.get("site")),
                company=str(r.get("company") or ""),
                title=str(r.get("title") or ""),
                location=str(r.get("location") or ""),
                url=url,
                apply_url=direct if direct and direct != "nan" else "",  # empty => aggregator-only listing
                description=str(r.get("description") or "") if str(r.get("description")) != "nan" else "",
            ))
        print(f"[discovery] jobspy '{s.term}' @ {s.location}: {len(df)} results")
    return [j for j in out if prefilter(j, profile)]


def discover(profile: Profile) -> list[Job]:
    found: list[Job] = jobboards(profile)
    for emp in profile.sources.get("workday", []):
        if not isinstance(emp, dict) or not {"base_url", "tenant", "site_id"} <= emp.keys():
            print(f"[discovery] workday entry needs base_url, tenant, site_id: {emp}")
            continue
        try:
            jobs = workday(emp, profile.preferences.target_titles)
        except Exception as e:
            print(f"[discovery] workday/{emp.get('name', emp['tenant'])} failed: {e}")
            continue
        kept = [j for j in jobs if prefilter(j, profile)]
        for j in kept:
            fill_workday_description(emp, j)
        print(f"[discovery] workday/{emp.get('name', emp['tenant'])}: {len(jobs)} jobs, {len(kept)} pass filters")
        found.extend(kept)
    for ats, boards in profile.sources.items():
        if ats == "workday":
            continue
        fetch = FETCHERS.get(ats)
        if not fetch:
            print(f"[discovery] unknown source '{ats}', skipping")
            continue
        for b in boards:
            try:
                jobs = fetch(b)
            except Exception as e:  # one bad board shouldn't kill the run
                print(f"[discovery] {ats}/{b} failed: {e}")
                continue
            kept = [j for j in jobs if prefilter(j, profile)]
            print(f"[discovery] {ats}/{b}: {len(jobs)} jobs, {len(kept)} pass filters")
            found.extend(kept)
    return found
