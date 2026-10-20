from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone

from .config import OUTPUT_DIR, ROOT, load_profile
from .models import Job, Tailored
from .store import Store


def cmd_init(a) -> None:
    for src, dst in [("profile.example.yaml", "profile.yaml"), (".env.example", ".env")]:
        if (ROOT / dst).exists():
            print(f"= {dst} already exists, leaving it alone")
        else:
            shutil.copy(ROOT / src, ROOT / dst)
            print(f"+ created {dst}")
    print("\nNext: put your key in .env (GEMINI_API_KEY is free), fill profile.yaml, add resume.pdf, then `run`.")


def cmd_setup(a) -> None:
    from .wizard import run

    run(a.resume, use_ai=not a.no_ai)
    print("\nNext: `python -m applyforme run`.")


def cmd_import_resume(a) -> None:
    """Parse uploaded resume.pdf into profile.yaml (non-interactive)."""
    from .import_resume import import_resume_file

    info = import_resume_file(a.path)
    print(
        f"\nImported {info.get('name') or 'contact'}, {info['roles']} roles, "
        f"{info['skills']} skills, {info['education']} education, "
        f"{info.get('projects', 0)} projects, {info.get('honors', 0)} honors → profile.yaml"
    )
    print("Profile fields auto-filled. Tailor will use this for per-job PDFs.")


def cmd_discover(a) -> None:
    from .agents.discovery import discover

    profile, store = load_profile(a.profile), Store()
    if not profile.preferences.wants_jobs():
        print(f"search_focus={profile.preferences.search_focus!r} — skipping full-time discover (use `internships`).")
        return
    new = sum(store.add_job(j) for j in discover(profile))
    print(f"\n{new} new jobs saved. Stats: {store.stats()}")
    _sweep(store)


def cmd_internships(a) -> None:
    """Fetch internship-only roles (Glassdoor, Wellfound, LinkedIn, Indeed, Remotive, …)."""
    from .agents.discovery import discover_internships

    profile, store = load_profile(a.profile), Store()
    if not profile.preferences.wants_internships():
        print(f"search_focus={profile.preferences.search_focus!r} — skipping internships (set focus to internships or both).")
        return
    jobs = discover_internships(profile)[: a.limit]
    new = sum(store.add_job(j, category="Internship") for j in jobs)
    print(f"\n{new} new internships saved ({len(jobs)} fetched). Stats: {store.stats()}")

    # Internships used to sit at status=new forever (never scored). Score them
    # here so low-relevance roles fall to `skipped` and high ones reach `matched`.
    rows = store.db.execute(
        "SELECT * FROM jobs WHERE status='new' AND category='Internship'"
        " ORDER BY updated_at DESC LIMIT ?",
        (a.limit,),
    ).fetchall()
    scored = 0
    for row in rows:
        job = Job.model_validate_json(row["job_json"])
        try:
            _enrich_job(store, job)
            r, ok = _score_job(store, profile, job)
        except Exception as e:
            print(f"! {job.title} @ {job.company}: {e}")
            continue
        scored += 1
        print(f"{r.score:3d} {'+' if ok else '-'} {job.title} @ {job.company}")
    if scored:
        print(f"{scored} internships scored. Stats: {store.stats()}")
    _sweep(store)


def _enrich_job(store, job: Job) -> None:
    """Fill a missing description (web page / JSON-LD / LLM cascade)."""
    from .agents.enrich import enrich

    if len(job.description) >= 300:
        return
    job.description = enrich(job)
    store.db.execute(
        "UPDATE jobs SET job_json=?, url=?, company=? WHERE id=?",
        (job.model_dump_json(), job.url, job.company, job.id),
    )
    store.db.commit()


def _score_job(store, profile, job: Job):
    """Score one job and move it to matched / skipped."""
    from .agents.matcher import match

    r = match(job, profile)
    ok = r.score >= profile.preferences.min_match_score
    store.update(
        job.id,
        score=r.score,
        reasons=json.dumps({"reasons": r.reasons, "red_flags": r.red_flags, "keywords": r.keywords}),
        status="matched" if ok else "skipped",
    )
    return r, ok


def _sweep(store: Store) -> None:
    """Remove cross-board duplicates and stale listings after a fetch."""
    dupes = store.dedupe_jobs()
    stale = store.prune_stale()
    if dupes:
        print(f"[cleanup] removed {len(dupes)} duplicate listing(s)")
    if stale:
        print(f"[cleanup] removed {len(stale)} stale listing(s) (older than JOB_RETENTION_DAYS)")


def cmd_cleanup(a) -> None:
    """Maintenance: drop duplicates, stale listings, and off-target internships."""
    from .agents.discovery import internship_prefilter

    profile, store = load_profile(a.profile), Store()
    dry = a.dry_run
    verb = "would remove" if dry else "removed"

    dupes = store.dedupe_jobs(dry_run=dry)
    stale = store.prune_stale(days=a.days, dry_run=dry)

    irrelevant: list[str] = []
    rows = store.db.execute(
        "SELECT * FROM jobs WHERE category='Internship' AND status IN ('new','skipped')"
    ).fetchall()
    for row in rows:
        try:
            job = Job.model_validate_json(row["job_json"])
        except Exception:
            continue
        if not internship_prefilter(job, profile):
            irrelevant.append(row["id"])
    already = set(dupes) | set(stale)
    irrelevant = [i for i in irrelevant if i not in already]
    if irrelevant and not dry:
        store.delete_jobs(irrelevant)

    print(f"[cleanup] {verb}: {len(dupes)} duplicate(s), {len(stale)} stale (>{a.days}d), {len(irrelevant)} off-target internship(s)")
    print(f"[cleanup] remaining: {store.stats()}")
    if dry and (dupes or stale or irrelevant):
        print("[cleanup] dry run — re-run without --dry-run to apply.")


def cmd_enrich(a) -> None:
    from . import crustdata
    from .agents.enrich import enrich

    crustdata.reset_run_budget()
    store = Store()
    rows = store.by_status("new", a.limit)
    # One budgeted pass for company firmographics (not once-per-job unbounded)
    if crustdata.enabled():
        jobs_preview = [Job.model_validate_json(r["job_json"]) for r in rows]
        crustdata.enrich_jobs_budgeted(jobs_preview)
        by_id = {j.id: j for j in jobs_preview}
    else:
        by_id = {}

    for row in rows:
        job = by_id.get(row["id"]) or Job.model_validate_json(row["job_json"])
        try:
            if len(job.description) < 300:
                job.description = enrich(job)
            store.db.execute(
                "UPDATE jobs SET job_json=?, url=?, company=? WHERE id=?",
                (job.model_dump_json(), job.url, job.company, job.id),
            )
            store.db.commit()
            print(f"enriched: {job.title} @ {job.company}  post={job.url}  careers={job.careers_url or '-'}")
        except Exception as e:
            print(f"! enrich failed {job.url}: {e}")
    if crustdata.enabled():
        print(f"[enrich] crustdata spend this run: ~{crustdata.credits_spent():.2f} credits")


def cmd_match(a) -> None:
    profile, store = load_profile(a.profile), Store()
    for row in store.by_status("new", a.limit):
        job = Job.model_validate_json(row["job_json"])
        try:
            r, ok = _score_job(store, profile, job)
        except Exception as e:
            print(f"! {job.title} @ {job.company}: {e}")
            continue
        print(f"{r.score:3d} {'+' if ok else '-'} {job.title} @ {job.company}")


def cmd_tailor(a) -> None:
    import time
    from concurrent.futures import ThreadPoolExecutor

    from .agents.resume import build_pdf
    from .agents.tailor import tailor

    profile, store = load_profile(a.profile), Store()
    job_id = getattr(a, "job_id", None)
    rows = [store.get(job_id)] if job_id else store.by_status("matched", a.limit)
    for row in rows:
        if not row:
            print(f"Job not found: {job_id}")
            continue
        if row["status"] not in ("matched", "ready", "manual") and job_id:
            print(f"Skip {row['id']}: status={row['status']} (need matched/ready)")
            continue
        job = Job.model_validate_json(row["job_json"])
        try:
            kw = (json.loads(row["reasons"] or "{}")).get("keywords") or []
        except (ValueError, TypeError):
            kw = []
        t0 = time.perf_counter()
        print(f"[tailor] {job.title} @ {job.company} — cover letter ∥ resume PDF (LLM + Chromium)…")
        try:
            # Cover letter and resume are independent — run in parallel (was sequential ≈ 2× slower).
            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_cover = pool.submit(tailor, job, profile, kw)
                fut_pdf = pool.submit(build_pdf, job, profile, kw)
                t = fut_cover.result()
                pdf, tex_path, warns = fut_pdf.result()
        except Exception as e:
            print(f"! tailor failed {job.title} @ {job.company}: {e}")
            if job_id:
                raise SystemExit(1) from e
            continue
        t.resume_pdf, t.resume_tex = pdf, tex_path
        (OUTPUT_DIR / f"{job.id.replace(':', '_')}.cover.txt").write_text(t.cover_letter, encoding="utf-8")
        store.update(job.id, cover_letter=t.model_dump_json(), status="ready", notes="; ".join(warns)[:200] or None)
        flag = f"  (used original resume content: {warns[0]})" if warns else ""
        print(f"tailored in {time.perf_counter() - t0:.1f}s: {job.title} @ {job.company}{flag}")


def cmd_list(a) -> None:
    store = Store()
    print(store.stats())
    for row in store.by_status(a.status, a.limit):
        print(f"{row['score'] or '-':>4}  {row['id']:<45} {row['title']} @ {row['company']}\n      {row['url']}")


def cmd_apply(a) -> None:
    from .agents.applier import apply
    from .agents.routing import manual_reason
    from .browser_runtime import ensure_playwright_browsers_path

    ensure_playwright_browsers_path()

    profile, store = load_profile(a.profile), Store()
    if a.cancel:
        if not a.job_id:
            print("--cancel needs a job id")
            return
        store.request_apply_cancel(a.job_id)
        print(f"-> cancellation requested for {a.job_id}")
        return
    rows = [store.get(a.job_id)] if a.job_id else store.by_status("ready", a.limit)
    for row in rows:
        if not row or not row["cover_letter"]:
            print("Job missing or not tailored yet (run `tailor` first).")
            continue
        job = Job.model_validate_json(row["job_json"])
        target = (job.apply_url or job.url or "").strip()
        print(f"\n=== {job.title} @ {job.company} ===\n{target}")
        if not target:
            msg = "no posting URL to open in the browser"
            store.update(job.id, notes=msg)
            print(f"-> skipped: {msg}")
            continue
        if store.submission_recorded(job.id):
            store.update(job.id, status="applied", notes=None)
            print("-> already submitted and confirmed; skipping")
            continue
        # LinkedIn / Indeed / Glassdoor: open the listing in Chromium (Easy Apply included).
        # Only hard-block non-LinkedIn SSO / Workday-style walls before launch.
        pre_url = target
        if "linkedin.com" not in pre_url.lower() and (why := manual_reason(pre_url)):
            store.update(job.id, status="manual", notes=why[:200])
            store.add_event(job.id, "manual", f"Apply manually: {job.title} @ {job.company}", why)
            print(f"-> apply manually: {why}")
            continue
        try:
            store.update(job.id, status="in_progress", notes="application in progress")
            res, note = apply(
                job, profile, Tailored.model_validate_json(row["cover_letter"]),
                store=store, dry_run=a.dry_run, auto_submit=a.yes, ask_terminal=a.ask,
                authorize_submit=bool(a.submit or a.yes),
            )
            if res == "applied":
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                store.update(job.id, status="applied", applied_at=now, notes=None)
                store.add_event(job.id, "submitted", f"Application submitted to {job.company}", job.url)
            elif res == "already_submitted":
                store.update(job.id, status="applied", notes=None)
            elif res == "awaiting_review":
                store.update(job.id, status="awaiting_review", notes=(note or "waiting for your review")[:200])
                store.add_event(job.id, "awaiting_review", f"Ready for review: {job.title} @ {job.company}", note or "")
            elif res == "needs_feedback":
                store.update(job.id, status="needs_feedback", notes=note)
            elif res == "manual":
                store.update(job.id, status="manual", notes=note[:200])
                store.add_event(job.id, "manual", f"Apply manually: {job.title} @ {job.company}", note)
            elif res == "blocked":
                store.update(job.id, status="blocked", notes=note[:200])
                store.add_event(job.id, "blocked", f"Application blocked: {job.title} @ {job.company}", note)
            elif res == "closed":
                store.update(job.id, status="skipped", notes=note[:200])
            elif res == "cancelled":
                store.update(job.id, status="cancelled", notes=note[:200])
            elif res == "busy":
                # Another worker owns this application; leave it retryable.
                store.update(job.id, status="ready", notes=note[:200])
                print(f"-> busy: {note}")
            elif res == "filled":
                store.update(job.id, status="awaiting_review", notes=(note or "dry run")[:200])
            elif res == "unverified":
                # Submit was clicked but no confirmation — caution: may already be sent.
                store.update(job.id, status="failed", notes=note[:200])
                store.add_event(job.id, "failed", f"Could not confirm submission to {job.company}", note)
            elif res == "errors":
                # Automation glitch before a confirmed submit — NOT a rejected
                # application. Keep it reviewable so the user can retry.
                store.update(job.id, status="ready", notes=note[:200])
                store.add_event(job.id, "apply_error", f"Apply interrupted for {job.company}", note)
            print(f"-> {res}: {note}")
        except Exception as e:
            store.update(job.id, status="ready", notes=str(e)[:200])
            store.add_event(job.id, "apply_error", f"Apply error for {job.company}", str(e)[:500])
            print(f"-> apply error (still ready to retry): {e}")


def cmd_dashboard(a) -> None:
    """Start the Next.js dashboard + background worker so the UI can trigger agents without a second terminal."""
    import subprocess
    import secrets

    Store()
    # Ensure webhook secret exists so EC2/EventBridge and local UI share one path.
    env_path = ROOT / ".env"
    if env_path.exists() and "PIPELINE_WEBHOOK_SECRET=" not in env_path.read_text(encoding="utf-8", errors="ignore"):
        with open(env_path, "a", encoding="utf-8") as f:
            f.write(f"\nPIPELINE_WEBHOOK_SECRET={secrets.token_hex(32)}\n")
        print("+ wrote PIPELINE_WEBHOOK_SECRET to .env")

    web = ROOT / "dashboard"
    if not (web / "node_modules").exists():
        print("Installing dashboard dependencies (first run)...")
        subprocess.run(["npm.cmd" if os.name == "nt" else "npm", "install"], cwd=web, check=True)

    # Background worker (cron + /hooks). Dashboard also spawns Python if this isn't up.
    worker = None
    if not a.no_worker:
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        worker = subprocess.Popen(
            [os.environ.get("APPLYFORME_PYTHON") or __import__("sys").executable, "-m", "applyforme", "serve",
             "--host", "127.0.0.1", "--port", str(a.worker_port)],
            cwd=str(ROOT),
            env=env,
        )
        print(f"Worker:    http://127.0.0.1:{a.worker_port}/health  (pid {worker.pid})")

    print(f"Dashboard: http://localhost:{a.port}")
    print("Open the app → Finish onboarding → jobs search starts automatically.")
    try:
        subprocess.run(
            ["npm.cmd" if os.name == "nt" else "npm", "run", "dev", "--", "-p", str(a.port)],
            cwd=web,
        )
    finally:
        if worker and worker.poll() is None:
            worker.terminate()


def cmd_inbox(a) -> None:
    from .inbox import poll

    poll(a.days)


def cmd_serve(a) -> None:
    """EC2 worker: cron scheduler + authenticated webhooks (see applyforme/serve.py)."""
    from .serve import main as serve_main

    serve_main(["--host", a.host, "--port", str(a.port)] + (["--no-scheduler"] if a.no_scheduler else []))


def cmd_run(a) -> None:
    profile = load_profile(a.profile)
    focus = (profile.preferences.search_focus or "jobs").lower()
    print(f"[run] search_focus={focus}")
    if profile.preferences.wants_jobs():
        cmd_discover(a)
        cmd_enrich(a)
        cmd_match(a)
        cmd_tailor(a)
    if profile.preferences.wants_internships():
        cmd_internships(a)
    print("\nReady to apply. Review with `list --status ready`, then `apply --dry-run`.")


def main() -> None:
    p = argparse.ArgumentParser(prog="applyforme", description="Agentic job application pipeline")
    p.add_argument("--profile", default=None, help="path to profile yaml (default ./profile.yaml)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create profile.yaml and .env from examples").set_defaults(fn=cmd_init)
    s = sub.add_parser("setup", help="interactive wizard: build profile.yaml from your resume (recommended first step)")
    s.add_argument("--resume", default=None, help="path to your resume PDF/txt")
    s.add_argument("--no-ai", action="store_true", help="skip resume auto-import, answer everything manually")
    s.set_defaults(fn=cmd_setup)
    s = sub.add_parser(
        "import-resume",
        help="parse resume.pdf into profile.yaml (non-interactive; used after dashboard upload)",
    )
    s.add_argument("--path", default=None, help="resume file (default: resume.pdf / profile resume_path)")
    s.set_defaults(fn=cmd_import_resume)
    for name, fn, help_ in [
        ("discover", cmd_discover, "1. fetch jobs: JobSpy boards + Greenhouse/Lever/Ashby/Workday"),
        ("internships", cmd_internships, "fetch internships from Glassdoor, Wellfound, LinkedIn, Indeed, Remotive"),
        ("enrich", cmd_enrich, "2. fetch full descriptions for jobs missing them"),
        ("match", cmd_match, "3. score new jobs against your profile"),
        ("run", cmd_run, "stages 1-5 in one go"),
    ]:
        s = sub.add_parser(name, help=help_)
        s.add_argument("--limit", type=int, default=50)
        s.set_defaults(fn=fn)

    s = sub.add_parser("tailor", help="4+5. tailored resume PDF + cover letter for matched jobs")
    s.add_argument("job_id", nargs="?", help="specific job id; default = all matched jobs")
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(fn=cmd_tailor)

    s = sub.add_parser("list", help="show jobs by status")
    s.add_argument(
        "--status",
        default="ready",
        choices=[
            "new", "matched", "skipped", "ready", "needs_feedback", "manual",
            "in_progress", "awaiting_review", "blocked", "cancelled", "applied", "failed",
        ],
    )
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("cleanup", help="maintenance: remove duplicate / stale / off-target listings")
    s.add_argument(
        "--days",
        type=int,
        default=int(os.getenv("JOB_RETENTION_DAYS", "10")),
        help="drop untouched listings older than N days (0 disables)",
    )
    s.add_argument("--dry-run", action="store_true", help="show what would be removed without deleting")
    s.set_defaults(fn=cmd_cleanup)

    s = sub.add_parser("apply", help="6. fill (and submit with approval) applications for ready jobs")
    s.add_argument("job_id", nargs="?", help="specific job id; default = all ready jobs")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--dry-run", action="store_true", help="fill the form but never submit")
    s.add_argument("--yes", action="store_true", help="explicitly authorize submission (use with care)")
    s.add_argument("--submit", action="store_true", help="explicitly authorize submission after a prepared review")
    s.add_argument("--cancel", action="store_true", help="request cancellation of a running application (needs job_id)")
    s.add_argument("--ask", action="store_true", help="ask unknown required questions in the terminal instead of saving them to the dashboard")
    s.set_defaults(fn=cmd_apply)

    s = sub.add_parser("dashboard", help="start the Next.js dashboard + background agent worker")
    s.add_argument("--port", type=int, default=3000)
    s.add_argument("--worker-port", type=int, default=8787)
    s.add_argument("--no-worker", action="store_true", help="dashboard only (UI can still spawn Python locally)")
    s.set_defaults(fn=cmd_dashboard)

    s = sub.add_parser("inbox", help="match employer emails (IMAP, read-only) to applied jobs")
    s.add_argument("--days", type=int, default=14)
    s.set_defaults(fn=cmd_inbox)

    s = sub.add_parser("serve", help="EC2 worker: cron scheduler + Bearer-auth webhooks (POST /hooks/run)")
    s.add_argument("--host", default=None, help="bind address (default PIPELINE_HOST or 127.0.0.1)")
    s.add_argument("--port", type=int, default=None, help="port (default PIPELINE_PORT or 8787)")
    s.add_argument("--no-scheduler", action="store_true", help="webhooks only; use EventBridge/cron externally")
    s.set_defaults(fn=cmd_serve)

    a = p.parse_args()
    # Fill serve defaults from env after parse (argparse default=None so env wins when flag omitted).
    if a.cmd == "serve":
        a.host = a.host or os.getenv("PIPELINE_HOST", "127.0.0.1")
        a.port = a.port or int(os.getenv("PIPELINE_PORT", "8787"))
    a.fn(a)


if __name__ == "__main__":
    main()
