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


def cmd_discover(a) -> None:
    from .agents.discovery import discover

    profile, store = load_profile(a.profile), Store()
    new = sum(store.add_job(j) for j in discover(profile))
    print(f"\n{new} new jobs saved. Stats: {store.stats()}")


def cmd_enrich(a) -> None:
    from .agents.enrich import enrich

    store = Store()
    for row in store.by_status("new", a.limit):
        job = Job.model_validate_json(row["job_json"])
        if len(job.description) >= 300:
            continue
        try:
            job.description = enrich(job)
            store.db.execute("UPDATE jobs SET job_json=? WHERE id=?", (job.model_dump_json(), job.id))
            store.db.commit()
            print(f"enriched ({len(job.description)} chars): {job.title} @ {job.company}")
        except Exception as e:
            print(f"! enrich failed {job.url}: {e}")


def cmd_match(a) -> None:
    from .agents.matcher import match

    profile, store = load_profile(a.profile), Store()
    for row in store.by_status("new", a.limit):
        job = Job.model_validate_json(row["job_json"])
        try:
            r = match(job, profile)
        except Exception as e:
            print(f"! {job.title} @ {job.company}: {e}")
            continue
        ok = r.score >= profile.preferences.min_match_score
        store.update(job.id, score=r.score, reasons=json.dumps({"reasons": r.reasons, "red_flags": r.red_flags, "keywords": r.keywords}), status="matched" if ok else "skipped")
        print(f"{r.score:3d} {'+' if ok else '-'} {job.title} @ {job.company}")


def cmd_tailor(a) -> None:
    from .agents.resume import build_pdf
    from .agents.tailor import tailor

    profile, store = load_profile(a.profile), Store()
    for row in store.by_status("matched", a.limit):
        job = Job.model_validate_json(row["job_json"])
        try:
            kw = (json.loads(row["reasons"] or "{}")).get("keywords") or []
        except (ValueError, TypeError):
            kw = []
        try:
            t = tailor(job, profile, kw)
            pdf, tex_path, warns = build_pdf(job, profile, kw)
        except Exception as e:
            print(f"! tailor failed {job.title} @ {job.company}: {e}")
            continue
        t.resume_pdf, t.resume_tex = pdf, tex_path
        (OUTPUT_DIR / f"{job.id.replace(':', '_')}.cover.txt").write_text(t.cover_letter, encoding="utf-8")
        store.update(job.id, cover_letter=t.model_dump_json(), status="ready", notes="; ".join(warns)[:200] or None)
        flag = f"  (used original resume content: {warns[0]})" if warns else ""
        print(f"tailored: {job.title} @ {job.company}{flag}")


def cmd_list(a) -> None:
    store = Store()
    print(store.stats())
    for row in store.by_status(a.status, a.limit):
        print(f"{row['score'] or '-':>4}  {row['id']:<45} {row['title']} @ {row['company']}\n      {row['url']}")


def cmd_apply(a) -> None:
    from .agents.applier import apply
    from .agents.discovery import AGGREGATORS
    from .agents.routing import manual_reason

    profile, store = load_profile(a.profile), Store()
    rows = [store.get(a.job_id)] if a.job_id else store.by_status("ready", a.limit)
    for row in rows:
        if not row or not row["cover_letter"]:
            print("Job missing or not tailored yet (run `tailor` first).")
            continue
        job = Job.model_validate_json(row["job_json"])
        print(f"\n=== {job.title} @ {job.company} ===\n{job.url}")
        if job.ats in AGGREGATORS and not job.apply_url:
            msg = "aggregator-only listing (needs login/Easy Apply) - apply manually via the link"
            store.update(job.id, notes=msg)
            print(f"-> skipped: {msg}")
            continue
        if why := manual_reason(job.apply_url or job.url):
            store.update(job.id, status="manual", notes=why[:200])
            store.add_event(job.id, "manual", f"Apply manually: {job.title} @ {job.company}", why)
            print(f"-> apply manually: {why}")
            continue
        try:
            res, note = apply(
                job, profile, Tailored.model_validate_json(row["cover_letter"]),
                store=store, dry_run=a.dry_run, auto_submit=a.yes, ask_terminal=a.ask,
            )
            if res == "applied":
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                store.update(job.id, status="applied", applied_at=now, notes=None)
                store.add_event(job.id, "submitted", f"Application submitted to {job.company}", job.url)
            elif res == "needs_feedback":
                store.update(job.id, status="needs_feedback", notes=note)
            elif res == "manual":
                store.update(job.id, status="manual", notes=note[:200])
                store.add_event(job.id, "manual", f"Apply manually: {job.title} @ {job.company}", note)
            elif res == "closed":
                store.update(job.id, status="skipped", notes=note[:200])
            elif res in ("errors", "unverified"):
                # Don't mark applied, and don't leave it 'ready' where a re-run could double-submit.
                store.update(job.id, status="failed", notes=note[:200])
                store.add_event(job.id, "failed", f"Could not confirm submission to {job.company}", note)
            print(f"-> {res}: {note}")
        except Exception as e:
            store.update(job.id, status="failed", notes=str(e)[:200])
            print(f"-> failed: {e}")


def cmd_dashboard(a) -> None:
    """Start the Next.js dashboard (dashboard/). Opening the Store first guarantees the DB schema exists."""
    import subprocess

    Store()
    web = ROOT / "dashboard"
    if not (web / "node_modules").exists():
        print("Installing dashboard dependencies (first run)...")
        subprocess.run(["npm.cmd" if os.name == "nt" else "npm", "install"], cwd=web, check=True)
    print(f"Dashboard: http://localhost:{a.port}")
    subprocess.run(["npm.cmd" if os.name == "nt" else "npm", "run", "dev", "--", "-p", str(a.port)], cwd=web)


def cmd_inbox(a) -> None:
    from .inbox import poll

    poll(a.days)


def cmd_serve(a) -> None:
    """EC2 worker: cron scheduler + authenticated webhooks (see applyforme/serve.py)."""
    from .serve import main as serve_main

    serve_main(["--host", a.host, "--port", str(a.port)] + (["--no-scheduler"] if a.no_scheduler else []))


def cmd_run(a) -> None:
    cmd_discover(a)
    cmd_enrich(a)
    cmd_match(a)
    cmd_tailor(a)
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
    for name, fn, help_ in [
        ("discover", cmd_discover, "1. fetch jobs from ATS boards (+ job boards if `searches` set)"),
        ("enrich", cmd_enrich, "2. fetch full descriptions for jobs missing them"),
        ("match", cmd_match, "3. score new jobs against your profile"),
        ("tailor", cmd_tailor, "4+5. tailored resume PDF + cover letter for matched jobs"),
        ("run", cmd_run, "stages 1-5 in one go"),
    ]:
        s = sub.add_parser(name, help=help_)
        s.add_argument("--limit", type=int, default=50)
        s.set_defaults(fn=fn)

    s = sub.add_parser("list", help="show jobs by status")
    s.add_argument("--status", default="ready", choices=["new", "matched", "skipped", "ready", "needs_feedback", "manual", "applied", "failed"])
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("apply", help="6. fill (and submit with approval) applications for ready jobs")
    s.add_argument("job_id", nargs="?", help="specific job id; default = all ready jobs")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--dry-run", action="store_true", help="fill the form but never submit")
    s.add_argument("--yes", action="store_true", help="skip the approval prompt (use with care)")
    s.add_argument("--ask", action="store_true", help="ask unknown required questions in the terminal instead of saving them to the dashboard")
    s.set_defaults(fn=cmd_apply)

    s = sub.add_parser("dashboard", help="start the Next.js dashboard")
    s.add_argument("--port", type=int, default=3000)
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
        import os
        a.host = a.host or os.getenv("PIPELINE_HOST", "127.0.0.1")
        a.port = a.port or int(os.getenv("PIPELINE_PORT", "8787"))
    a.fn(a)


if __name__ == "__main__":
    main()
