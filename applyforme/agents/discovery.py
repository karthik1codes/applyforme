"""Discovery agent: pulls open roles from public ATS job-board APIs (no scraping/login)."""
from __future__ import annotations

import re

import httpx

from ..models import Job, Profile

TIMEOUT = 30

# Values a user (or an older onboarding screen) may leave in a title field.
_PLACEHOLDER_TITLES = {
    "", "-", "none", "n/a", "na", "n.a.", "null", "nil", "any", "unknown", "not sure", "tbd",
}

# Last-resort search titles when the profile has no usable target titles.
DEFAULT_TITLES = [
    "software engineer",
    "data analyst",
    "data scientist",
    "machine learning engineer",
    "backend engineer",
]

_ROLE_WORDS = {
    "engineer", "engineering", "developer", "development", "intern", "internship",
    "trainee", "apprentice", "co", "op", "senior", "junior", "lead", "staff",
    "principal", "associate", "manager", "specialist", "remote",
}

# Titles that are non-technical even when they mention AI/data as a buzzword
# ("Marketing Intern - AI Video"). Rejected unless a strong technical word is
# also present ("Data Analytics & Finance Accounting" stays).
_NON_TECH_TITLE_WORDS = {
    "marketing", "sales", "social", "media", "graphic", "creative", "content",
    "brand", "finance", "accounting", "investment", "banker", "mechanical",
    "civil", "hr", "human", "resources", "recruitment", "legal", "customer",
    "support", "operations", "product", "management", "business", "leadership",
    "communication", "teamwork", "presentation", "organization", "planning",
}

# Soft skills in a profile must not make an unrelated internship "relevant".
_SOFT_TOKENS = {
    "leadership", "communication", "teamwork", "team", "presentation",
    "organization", "planning", "event", "events", "management",
}
_STRONG_TECH_TITLE_WORDS = {
    "software", "data", "analytics", "analyst", "science", "scientist",
    "backend", "frontend", "fullstack", "python", "java", "javascript",
    "typescript", "react", "node", "sql", "database", "cloud", "devops",
    "sre", "security", "cyber", "qa", "automation", "android", "ios",
    "mobile", "embedded", "firmware", "blockchain", "nlp", "vision", "llm",
    "machine", "learning",
}

# Technical domains that make an internship worth scoring. Deliberately excludes
# marketing / sales / design so those never reach the matcher.
_TECH_TOKENS = {
    "software", "data", "analytics", "analyst", "science", "scientist", "machine",
    "learning", "artificial", "intelligence", "ai", "ml", "backend", "frontend",
    "fullstack", "cloud", "devops", "sre", "security", "cyber", "python", "java",
    "javascript", "typescript", "react", "node", "sql", "database", "api",
    "platform", "infrastructure", "systems", "network", "embedded", "firmware",
    "android", "ios", "mobile", "qa", "automation", "research", "blockchain",
    "web3", "nlp", "vision", "llm",
}


def sanitized_titles(titles: list[str] | None) -> list[str]:
    """Drop blank / placeholder titles such as the literal ``none``."""
    out: list[str] = []
    for t in titles or []:
        s = (t or "").strip()
        if s.lower() in _PLACEHOLDER_TITLES:
            continue
        out.append(s)
    return out


def effective_titles(profile: Profile) -> list[str]:
    """Real target titles, falling back to the current role and then sensible defaults."""
    titles = sanitized_titles(profile.preferences.target_titles)
    if titles:
        return titles
    current = (profile.preferences.current_title or "").strip()
    if current.lower() not in _PLACEHOLDER_TITLES:
        return [current]
    return list(DEFAULT_TITLES)



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
    titles = effective_titles(profile)
    if not any(all(w in title for w in t.lower().split()) or t.lower() in title for t in titles):
        return False
    return location_ok(f"{job.location} {'remote' if 'remote' in title else ''}", p)


AGGREGATORS = {"indeed", "linkedin", "glassdoor", "zip_recruiter", "google"}
INTERNSHIP_SITES = ["glassdoor", "linkedin", "indeed", "zip_recruiter", "google", "naukri"]
_INTERN_RE = re.compile(r"\b(intern|internship|trainee|apprentice|co-?op|summer associate)\b", re.I)


def ensure_searches(profile: Profile) -> list:
    """Always search job boards. If profile.searches is empty, derive one query per target title."""
    from ..models import DEFAULT_BOARD_SITES, Search

    searches = [s for s in (profile.searches or []) if sanitized_titles([s.term])]
    if searches:
        # Force full board set even if an older profile only listed indeed/google.
        for s in searches:
            if not s.sites:
                s.sites = list(DEFAULT_BOARD_SITES)
        return searches

    titles = effective_titles(profile)
    locs = [l for l in profile.preferences.locations if l.strip().lower() != "remote"] or [""]
    location = locs[0] if locs else ""
    # Prefer the candidate's city from personal if locations were only "Remote"
    if not location and profile.personal.get("location"):
        location = str(profile.personal["location"])
    built = [
        Search(term=t, location=location, sites=list(DEFAULT_BOARD_SITES), results_wanted=25, hours_old=72)
        for t in titles
    ]
    print(f"[discovery] no usable searches in profile — using {len(built)} queries from target titles @ {location or '(any)'}")
    return built


def jobboards(profile: Profile) -> list[Job]:
    """Search Indeed, LinkedIn, Glassdoor, ZipRecruiter, and Google via python-jobspy (required)."""
    try:
        from jobspy import scrape_jobs
    except ImportError as e:
        raise SystemExit(
            "python-jobspy is required for discovery. Install with: pip install python-jobspy"
        ) from e

    searches = ensure_searches(profile)
    out: list[Job] = []
    for s in searches:
        sites = s.sites or list(AGGREGATORS)
        try:
            df = scrape_jobs(
                site_name=sites,
                search_term=s.term,
                location=s.location,
                results_wanted=s.results_wanted,
                hours_old=s.hours_old,
            )
        except Exception as e:
            print(f"[discovery] jobspy '{s.term}' on {sites} failed: {e}")
            continue
        n = 0 if df is None else len(df)
        for r in ([] if df is None else df.to_dict("records")):
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
                apply_url=direct if direct and direct != "nan" else "",  # empty => apply via listing link / manual
                description=str(r.get("description") or "") if str(r.get("description")) != "nan" else "",
            ))
        print(f"[discovery] jobspy '{s.term}' @ {s.location or 'any'} [{', '.join(sites)}]: {n} results")
    return [j for j in out if prefilter(j, profile)]


def _relevance_tokens(profile: Profile) -> set[str]:
    """Words that make a role plausibly relevant to this candidate (title + skills)."""
    tokens: set[str] = set(_TECH_TOKENS)
    for t in effective_titles(profile):
        for w in re.split(r"[^a-z0-9+#.]+", t.lower()):
            if len(w) > 2:
                tokens.add(w)
    for skill in profile.skills:
        s = (skill or "").strip().lower()
        if 2 < len(s) <= 24 and s not in _SOFT_TOKENS:
            tokens.add(s)
        for w in re.split(r"[^a-z0-9+#.]+", s):
            if len(w) > 2 and w not in _ROLE_WORDS and w not in _SOFT_TOKENS:
                tokens.add(w)
    return {t for t in tokens if t and t not in _ROLE_WORDS and t not in _SOFT_TOKENS}


def internship_prefilter(job: Job, profile: Profile) -> bool:
    """Keep only internships whose *title* matches a technical interest.

    The old version let every role through (a target title of ``none`` added no
    words), which is how marketing / sales / graphic-design internships ended up
    on the board. Requiring an intern signal in the title plus one relevance
    token keeps the matcher's budget for roles the user could actually take.
    """
    title = job.title.lower()
    if not _INTERN_RE.search(title):
        return False
    tokens = sorted(_relevance_tokens(profile))
    if not _has_any(tokens, title):
        return False
    if _has_any(sorted(_NON_TECH_TITLE_WORDS), title) and not _has_any(sorted(_STRONG_TECH_TITLE_WORDS), title):
        return False
    return location_ok(f"{job.location} {'remote' if 'remote' in title else ''}", profile.preferences)


def _jobspy_rows_to_jobs(df) -> list[Job]:
    out: list[Job] = []
    for r in ([] if df is None else df.to_dict("records")):
        url = str(r.get("job_url") or "")
        if not url:
            continue
        direct = str(r.get("job_url_direct") or "")
        out.append(
            Job(
                id=f"{r.get('site')}:{r.get('id') or url}",
                ats=str(r.get("site") or "board"),
                company=str(r.get("company") or ""),
                title=str(r.get("title") or ""),
                location=str(r.get("location") or ""),
                url=url,
                apply_url=direct if direct and direct != "nan" else "",
                description=str(r.get("description") or "") if str(r.get("description")) != "nan" else "",
            )
        )
    return out


def remotive_internships(query: str = "intern") -> list[Job]:
    """Remotive public API — remote roles (filter client-side for internship signal)."""
    try:
        r = httpx.get("https://remotive.com/api/remote-jobs", params={"search": query}, timeout=TIMEOUT, headers=_UA)
        r.raise_for_status()
    except Exception as e:
        print(f"[discovery] remotive failed: {e}")
        return []
    out: list[Job] = []
    for j in r.json().get("jobs") or []:
        title = j.get("title") or ""
        desc = _strip_html(j.get("description") or "")
        if not _INTERN_RE.search(f"{title} {desc[:400]}"):
            continue
        url = j.get("url") or ""
        if not url:
            continue
        out.append(
            Job(
                id=f"remotive:{j.get('id') or url}",
                ats="remotive",
                company=j.get("company_name") or "",
                title=title,
                location=j.get("candidate_required_location") or "Remote",
                url=url,
                apply_url=url,
                description=desc,
                company_website=j.get("company_logo_url") or "",
            )
        )
    print(f"[discovery] remotive internships: {len(out)}")
    return out


def wellfound_internships(terms: list[str], location: str = "") -> list[Job]:
    """Wellfound / AngelList via Google Jobs (JobSpy) — Wellfound has no stable public board API."""
    try:
        from jobspy import scrape_jobs
    except ImportError:
        return []
    out: list[Job] = []
    for term in terms[:4]:
        gterm = f'{term} internship (site:wellfound.com OR site:angel.co)'
        if location:
            gterm += f" {location}"
        try:
            df = scrape_jobs(
                site_name=["google"],
                search_term=f"{term} internship",
                google_search_term=gterm,
                location=location or "",
                results_wanted=15,
                hours_old=168,
            )
        except Exception as e:
            print(f"[discovery] wellfound/google '{term}' failed: {e}")
            continue
        jobs = _jobspy_rows_to_jobs(df)
        for j in jobs:
            j.ats = "wellfound" if "wellfound" in j.url or "angel.co" in j.url else j.ats
            j.id = f"wellfound:{j.id}" if not j.id.startswith("wellfound:") else j.id
        out.extend(jobs)
        print(f"[discovery] wellfound via google '{term}': {len(jobs)}")
    return out


def discover_internships(profile: Profile) -> list[Job]:
    """Internships from Glassdoor, LinkedIn, Indeed, Wellfound, Remotive, Google, Naukri, ZipRecruiter."""
    try:
        from jobspy import scrape_jobs
    except ImportError as e:
        raise SystemExit("python-jobspy is required. Install with: pip install python-jobspy") from e

    titles = effective_titles(profile)
    locs = [l for l in profile.preferences.locations if l.strip().lower() != "remote"] or [""]
    if not locs[0] and profile.personal.get("location"):
        locs = [str(profile.personal["location"])]
    location = locs[0] if locs else ""

    found: list[Job] = []
    # 1) Major boards with JobSpy internship filter (Glassdoor + LinkedIn + Indeed + …)
    for term in titles[:5]:
        search = f"{term} intern"
        try:
            df = scrape_jobs(
                site_name=list(INTERNSHIP_SITES),
                search_term=search,
                location=location,
                results_wanted=20,
                hours_old=168,
                job_type="internship",
            )
        except Exception as e:
            print(f"[discovery] internship jobspy '{search}' failed: {e}")
            # Retry without job_type — some sites reject the filter
            try:
                df = scrape_jobs(
                    site_name=list(INTERNSHIP_SITES),
                    search_term=f"{search}ship",
                    location=location,
                    results_wanted=20,
                    hours_old=168,
                )
            except Exception as e2:
                print(f"[discovery] internship jobspy retry failed: {e2}")
                continue
        jobs = _jobspy_rows_to_jobs(df)
        print(f"[discovery] internship boards '{search}' @ {location or 'any'}: {len(jobs)}")
        found.extend(jobs)

    # 2) Wellfound / AngelList (startup social) via Google
    found.extend(wellfound_internships(titles, location))

    # 3) Remotive remote internship feed
    found.extend(remotive_internships("intern"))

    # Deduplicate by URL / id
    seen: set[str] = set()
    uniq: list[Job] = []
    for j in found:
        key = j.url or j.id
        if key in seen:
            continue
        seen.add(key)
        if internship_prefilter(j, profile):
            uniq.append(j)
    print(f"[discovery] internships kept after filter: {len(uniq)}")
    return uniq


def discover(profile: Profile) -> list[Job]:
    """JobSpy boards + ATS boards; optional Crustdata job index (off by default — costs credits)."""
    from .. import crustdata

    crustdata.reset_run_budget()
    found: list[Job] = []
    # 1) Optional Crustdata indexed jobs (CRUSTDATA_JOB_SEARCH=1) — capped per run
    if crustdata.job_search_enabled():
        try:
            cd_jobs = crustdata.search_jobs(profile)
            kept = [j for j in cd_jobs if prefilter(j, profile)]
            print(f"[discovery] crustdata: {len(cd_jobs)} jobs, {len(kept)} pass filters")
            found.extend(kept)
        except Exception as e:
            print(f"[discovery] crustdata search failed: {e}")
    elif crustdata.enabled():
        print("[discovery] Crustdata job search disabled (set CRUSTDATA_JOB_SEARCH=1 to enable; costs credits)")
    else:
        print("[discovery] no CRUSTDATA_API_KEY — JobSpy + ATS boards only")

    # 2) Indeed / LinkedIn / Glassdoor / ZipRecruiter / Google (free)
    found.extend(jobboards(profile))
    for emp in profile.sources.get("workday", []):
        if not isinstance(emp, dict) or not {"base_url", "tenant", "site_id"} <= emp.keys():
            print(f"[discovery] workday entry needs base_url, tenant, site_id: {emp}")
            continue
        try:
            jobs = workday(emp, effective_titles(profile))
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

    # Cap paid company enrich (2 credits each) — unique employers only, budgeted
    if crustdata.enabled():
        crustdata.enrich_jobs_budgeted(found)
        print(f"[discovery] crustdata spend this run: ~{crustdata.credits_spent():.2f} credits")
    return found
