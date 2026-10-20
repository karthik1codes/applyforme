"""Long-running worker for EC2: cron scheduler + authenticated webhooks.

Replaces manually SSHing in to run `discover` / `run` / `inbox`.

  python -m applyforme serve --host 127.0.0.1 --port 8787

Env:
  PIPELINE_WEBHOOK_SECRET   required — Bearer token for POST /hooks/*
  SCHEDULE_RUN              cron (default "0 */4 * * *" = every 4 hours); empty to disable
  SCHEDULE_INBOX            cron (default "30 */6 * * *"); empty to disable
  SCHEDULE_LIMIT            int, default 40
  JOB_RETENTION_DAYS        drop untouched listings older than N days (default 10; 0 disables)
  ALLOW_AUTO_APPLY=1        required before a bulk POST /hooks/apply will prepare jobs
  POST /hooks/apply body {"job_id":..., "submit":true} submits ONE application
  after the dashboard records explicit one-shot authorization.
  POST /hooks/cleanup       maintenance: dedupe + drop stale / off-target listings
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import ROOT

# Per-lane locks so jobs ∥ internships (and apply/inbox) can run in parallel.
LANES = ("jobs", "internships", "apply", "inbox")
LOCKS: dict[str, threading.Lock] = {lane: threading.Lock() for lane in LANES}
STATE: dict[str, Any] = {"last": None, "running": {}, "history": []}
HISTORY_MAX = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _python() -> str:
    return sys.executable


def lane_for_stage(stage: str) -> str:
    if stage == "internships":
        return "internships"
    if stage == "apply":
        return "apply"
    if stage == "inbox":
        return "inbox"
    # cleanup / discover / enrich / match / tailor / run all use the jobs lane
    return "jobs"


def _set_dashboard_status(lane: str, payload: dict[str, Any]) -> None:
    """Mirror status into SQLite so the Next.js banner can poll without talking to the worker."""
    try:
        from .store import Store

        payload = {**payload, "lane": lane}
        Store().kv_set(f"pipeline_status:{lane}", json.dumps(payload))
    except Exception:
        pass


def run_stage(
    stage: str,
    *,
    limit: int = 40,
    extra: list[str] | None = None,
    submit: bool = False,
) -> dict[str, Any]:
    """Run one CLI stage. Serialized per lane — jobs and internships do not block each other."""
    if stage not in ("discover", "internships", "enrich", "match", "tailor", "run", "inbox", "apply", "cleanup"):
        return {"ok": False, "error": f"unknown stage {stage}"}
    lane = lane_for_stage(stage)
    lock = LOCKS[lane]
    if not lock.acquire(blocking=False):
        return {"ok": False, "error": f"{lane} pipeline already running", "running": STATE["running"].get(lane)}

    cmd = [_python(), "-m", "applyforme", stage]
    # Positional job id for apply / tailor (before flags)
    job_args = [a for a in (extra or []) if not a.startswith("-")]
    flag_args = [a for a in (extra or []) if a.startswith("-")]
    if stage in ("apply", "tailor") and job_args:
        cmd += job_args[:1]
    if stage == "inbox":
        cmd += ["--days", str(int(os.getenv("SCHEDULE_INBOX_DAYS", "14")))]
    elif stage == "cleanup":
        cmd += ["--days", str(int(os.getenv("JOB_RETENTION_DAYS", "10")))]
    else:
        cmd += ["--limit", str(limit)]
    if stage == "apply":
        # Prepare is the default: fill and stop for review.  A submit must be
        # one explicitly authorized job; never turn a bulk queue into blind
        # submissions.
        if submit:
            if not job_args:
                lock.release()
                return {"ok": False, "error": "submit requires one job_id (one explicit authorization per application)"}
            cmd += ["--submit"]
        elif not job_args and os.getenv("ALLOW_AUTO_APPLY") != "1":
            lock.release()
            return {"ok": False, "error": "ALLOW_AUTO_APPLY=1 required for bulk webhook apply (refuses blind submits)"}
    if flag_args:
        cmd += flag_args

    started = _now()
    STATE["running"][lane] = {"stage": stage, "lane": lane, "started": started, "cmd": cmd}
    _set_dashboard_status(lane, {
        "stage": stage,
        "state": "running",
        "startedAt": started,
        "finishedAt": None,
        "message": f"{lane} pipeline: running {stage}…",
    })
    try:
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env["APPLYFORME_PIPELINE_LANE"] = lane
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=int(os.getenv("PIPELINE_TIMEOUT_SEC", "3600")),
            env=env,
        )
        result = {
            "ok": proc.returncode == 0,
            "stage": stage,
            "lane": lane,
            "started": started,
            "finished": _now(),
            "exit_code": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        }
    except subprocess.TimeoutExpired:
        result = {"ok": False, "stage": stage, "lane": lane, "started": started, "finished": _now(), "error": "timeout"}
    except Exception as e:
        result = {"ok": False, "stage": stage, "lane": lane, "started": started, "finished": _now(), "error": str(e)}
    finally:
        STATE["running"].pop(lane, None)
        lock.release()

    finished = result.get("finished") or _now()
    ok_msg = {
        "run": "Done — open Jobs to see matches.",
        "internships": "Internship search done — open Internships.",
        "cleanup": "Cleanup done — stale and duplicate listings removed.",
    }.get(stage, f"{stage} finished.")
    _set_dashboard_status(lane, {
        "stage": stage,
        "state": "ok" if result.get("ok") else "error",
        "startedAt": started,
        "finishedAt": finished,
        "message": (
            ok_msg
            if result.get("ok")
            else (result.get("error") or result.get("stderr_tail") or result.get("stdout_tail") or f"{stage} failed")[-400:]
        ),
    })

    STATE["last"] = result
    STATE["history"] = ([result] + STATE["history"])[:HISTORY_MAX]
    log_path = ROOT / "data" / "pipeline.log"
    try:
        log_path.parent.mkdir(exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")
    except OSError:
        pass
    return result


def _authorized(handler: BaseHTTPRequestHandler) -> bool:
    secret = os.getenv("PIPELINE_WEBHOOK_SECRET", "").strip()
    if not secret:
        return False
    auth = handler.headers.get("Authorization", "")
    if auth == f"Bearer {secret}":
        return True
    return handler.headers.get("X-Pipeline-Secret", "") == secret


class Handler(BaseHTTPRequestHandler):
    server_version = "applyforme-worker/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, code: int, body: dict) -> None:
        raw = json.dumps(body, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/health"):
            return self._json(200, {
                "status": "ok",
                "service": "applyforme-worker",
                "running": STATE.get("running"),
                "last_ok": (STATE.get("last") or {}).get("ok"),
                "schedules": {
                    "run": os.getenv("SCHEDULE_RUN", "0 */4 * * *"),
                    "internships": os.getenv("SCHEDULE_INTERNSHIPS", "15 */6 * * *"),
                    "inbox": os.getenv("SCHEDULE_INBOX", "30 */6 * * *"),
                    "retention_days": os.getenv("JOB_RETENTION_DAYS", "10"),
                },
            })
        if path == "/status":
            if not _authorized(self):
                return self._json(401, {"error": "unauthorized"})
            return self._json(200, {"running": STATE["running"], "last": STATE["last"], "history": STATE["history"][:10]})
        return self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/hooks/"):
            return self._json(404, {"error": "not found"})
        if not _authorized(self):
            return self._json(401, {"error": "unauthorized — set Authorization: Bearer $PIPELINE_WEBHOOK_SECRET"})

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            body = {}
        qs = parse_qs(urlparse(self.path).query)
        limit = int(body.get("limit") or qs.get("limit", [os.getenv("SCHEDULE_LIMIT", "40")])[0])

        stage = path.removeprefix("/hooks/").strip("/")
        # Aliases
        if stage in ("pipeline", "full"):
            stage = "run"
        if stage not in ("discover", "internships", "enrich", "match", "tailor", "run", "inbox", "apply", "cleanup"):
            return self._json(400, {"error": f"unknown hook '{stage}'", "allowed": [
                "run", "discover", "internships", "enrich", "match", "tailor", "inbox", "apply", "cleanup",
            ]})

        extra: list[str] = []
        job_id = (body.get("job_id") or (qs.get("job_id") or [None])[0] or "").strip()
        if stage == "apply" and job_id:
            extra.append(job_id)
        submit = stage == "apply" and str(body.get("submit") or "").lower() in ("1", "true", "yes", "on")

        # Run in a background thread so the webhook returns quickly (EventBridge / cron won't time out).
        # Busy only if THIS lane is already running — jobs ∥ internships OK.
        async_mode = body.get("async", True)
        lane = lane_for_stage(stage)
        if async_mode:
            if STATE["running"].get(lane):
                return self._json(409, {"error": "busy", "lane": lane, "running": STATE["running"].get(lane)})
            threading.Thread(
                target=run_stage,
                kwargs={"stage": stage, "limit": limit, "extra": extra or None, "submit": submit},
                daemon=True,
            ).start()
            return self._json(202, {
                "accepted": True, "stage": stage, "lane": lane, "limit": limit,
                "job_id": job_id or None, "started": _now(),
            })
        return self._json(
            200 if (r := run_stage(stage, limit=limit, extra=extra or None, submit=submit)).get("ok") else 500,
            r,
        )


def _parse_cron(expr: str):
    """Return (minute, hour, day, month, dow) fields or None if disabled."""
    expr = (expr or "").strip()
    if not expr or expr.lower() in ("off", "false", "0", "disabled"):
        return None
    parts = expr.split()
    if len(parts) != 5:
        raise SystemExit(f"Invalid cron (need 5 fields): {expr!r}")
    return parts


def _cron_match(field: str, value: int, *, dow: bool = False) -> bool:
    if field == "*":
        return True
    for part in field.split(","):
        if part.startswith("*/"):
            step = int(part[2:])
            if value % step == 0:
                return True
        elif "-" in part:
            a, b = part.split("-", 1)
            if int(a) <= value <= int(b):
                return True
        elif int(part) == value:
            return True
    return False


def _should_fire(cron_parts: list[str], when: datetime) -> bool:
    minute, hour, day, month, dow = cron_parts
    # cron DOW: 0=Sunday … 6=Saturday; Python weekday(): 0=Monday … 6=Sunday
    py_dow = (when.weekday() + 1) % 7
    return (
        _cron_match(minute, when.minute)
        and _cron_match(hour, when.hour)
        and _cron_match(day, when.day)
        and _cron_match(month, when.month)
        and _cron_match(dow, py_dow, dow=True)
    )


def start_scheduler(stop: threading.Event) -> None:
    """Simple minute-resolution cron loop (no extra dependency). Jobs ∥ internships on separate lanes."""
    last_slot: str | None = None
    run_cron = _parse_cron(os.getenv("SCHEDULE_RUN", "0 */4 * * *"))
    inbox_cron = _parse_cron(os.getenv("SCHEDULE_INBOX", "30 */6 * * *"))
    intern_cron = _parse_cron(os.getenv("SCHEDULE_INTERNSHIPS", "15 */6 * * *"))
    limit = int(os.getenv("SCHEDULE_LIMIT", "40"))
    print(
        f"[scheduler] run={os.getenv('SCHEDULE_RUN', '0 */4 * * *')!r} "
        f"internships={os.getenv('SCHEDULE_INTERNSHIPS', '15 */6 * * *')!r} "
        f"inbox={os.getenv('SCHEDULE_INBOX', '30 */6 * * *')!r}"
    )

    while not stop.wait(15):
        now = datetime.now()
        slot = now.strftime("%Y-%m-%d %H:%M")
        if slot == last_slot:
            continue
        last_slot = slot
        try:
            # Honor profile search_focus so cron doesn't pull the wrong lane
            try:
                from .config import load_profile

                pref = load_profile().preferences
                want_jobs, want_interns = pref.wants_jobs(), pref.wants_internships()
            except Exception:
                want_jobs, want_interns = True, True

            if want_jobs and run_cron and _should_fire(run_cron, now):
                print(f"[scheduler] firing jobs lane (run) @ {slot}")
                threading.Thread(target=run_stage, kwargs={"stage": "run", "limit": limit}, daemon=True).start()
            if want_interns and intern_cron and _should_fire(intern_cron, now):
                print(f"[scheduler] firing internships lane @ {slot}")
                threading.Thread(target=run_stage, kwargs={"stage": "internships", "limit": limit}, daemon=True).start()
            if inbox_cron and _should_fire(inbox_cron, now):
                print(f"[scheduler] firing inbox lane @ {slot}")
                threading.Thread(target=run_stage, kwargs={"stage": "inbox", "limit": limit}, daemon=True).start()
        except Exception:
            traceback.print_exc()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="applyforme serve", description="Webhook + cron worker for EC2")
    p.add_argument("--host", default=os.getenv("PIPELINE_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.getenv("PIPELINE_PORT", "8787")))
    p.add_argument("--no-scheduler", action="store_true", help="webhooks only (use external EventBridge/cron)")
    args = p.parse_args(argv)

    if not os.getenv("PIPELINE_WEBHOOK_SECRET"):
        print("WARNING: PIPELINE_WEBHOOK_SECRET is empty — all /hooks/* will return 401 until you set it.", file=sys.stderr)

    stop = threading.Event()
    if not args.no_scheduler:
        threading.Thread(target=start_scheduler, args=(stop,), daemon=True).start()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[serve] listening on http://{args.host}:{args.port}")
    print(f"[serve] health:  GET  /health")
    print(f"[serve] status:  GET  /status   (Bearer)")
    print(f"[serve] trigger: POST /hooks/run|discover|match|tailor|inbox|apply  (Bearer)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        stop.set()
        httpd.shutdown()


if __name__ == "__main__":
    main()
