"""Long-running worker for EC2: cron scheduler + authenticated webhooks.

Replaces manually SSHing in to run `discover` / `run` / `inbox`.

  python -m applyforme serve --host 127.0.0.1 --port 8787

Env:
  PIPELINE_WEBHOOK_SECRET   required — Bearer token for POST /hooks/*
  SCHEDULE_RUN              cron (default "0 */4 * * *" = every 4 hours); empty to disable
  SCHEDULE_INBOX            cron (default "30 */6 * * *"); empty to disable
  SCHEDULE_LIMIT            int, default 40
  ALLOW_AUTO_APPLY=1        required before POST /hooks/apply will submit (--yes)
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

LOCK = threading.Lock()
STATE: dict[str, Any] = {"last": None, "running": None, "history": []}
HISTORY_MAX = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _python() -> str:
    return sys.executable


def run_stage(stage: str, *, limit: int = 40, extra: list[str] | None = None) -> dict[str, Any]:
    """Run one CLI stage as a subprocess. Serialized so two hooks can't overlap."""
    if stage not in ("discover", "enrich", "match", "tailor", "run", "inbox", "apply"):
        return {"ok": False, "error": f"unknown stage {stage}"}
    if not LOCK.acquire(blocking=False):
        return {"ok": False, "error": "another job is already running", "running": STATE.get("running")}

    cmd = [_python(), "-m", "applyforme", stage]
    if stage != "inbox":
        cmd += ["--limit", str(limit)]
    if stage == "inbox":
        cmd += ["--days", str(int(os.getenv("SCHEDULE_INBOX_DAYS", "14")))]
    if stage == "apply":
        if os.getenv("ALLOW_AUTO_APPLY") != "1":
            LOCK.release()
            return {"ok": False, "error": "ALLOW_AUTO_APPLY=1 required for webhook apply (refuses blind submits)"}
        cmd += ["--yes"]
    if extra:
        cmd += extra

    started = _now()
    STATE["running"] = {"stage": stage, "started": started, "cmd": cmd}
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=int(os.getenv("PIPELINE_TIMEOUT_SEC", "3600")),
            env=os.environ.copy(),
        )
        result = {
            "ok": proc.returncode == 0,
            "stage": stage,
            "started": started,
            "finished": _now(),
            "exit_code": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        }
    except subprocess.TimeoutExpired:
        result = {"ok": False, "stage": stage, "started": started, "finished": _now(), "error": "timeout"}
    except Exception as e:
        result = {"ok": False, "stage": stage, "started": started, "finished": _now(), "error": str(e)}
    finally:
        STATE["running"] = None
        LOCK.release()

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
                    "inbox": os.getenv("SCHEDULE_INBOX", "30 */6 * * *"),
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
        if stage not in ("discover", "enrich", "match", "tailor", "run", "inbox", "apply"):
            return self._json(400, {"error": f"unknown hook '{stage}'", "allowed": [
                "run", "discover", "enrich", "match", "tailor", "inbox", "apply",
            ]})

        # Run in a background thread so the webhook returns quickly (EventBridge / cron won't time out).
        async_mode = body.get("async", True)
        if async_mode:
            if STATE.get("running"):
                return self._json(409, {"error": "busy", "running": STATE["running"]})
            threading.Thread(target=run_stage, kwargs={"stage": stage, "limit": limit}, daemon=True).start()
            return self._json(202, {"accepted": True, "stage": stage, "limit": limit, "started": _now()})
        return self._json(200 if (r := run_stage(stage, limit=limit)).get("ok") else 500, r)


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
    """Simple minute-resolution cron loop (no extra dependency)."""
    last_slot: str | None = None
    run_cron = _parse_cron(os.getenv("SCHEDULE_RUN", "0 */4 * * *"))
    inbox_cron = _parse_cron(os.getenv("SCHEDULE_INBOX", "30 */6 * * *"))
    limit = int(os.getenv("SCHEDULE_LIMIT", "40"))
    print(f"[scheduler] run={os.getenv('SCHEDULE_RUN', '0 */4 * * *')!r} inbox={os.getenv('SCHEDULE_INBOX', '30 */6 * * *')!r}")

    while not stop.wait(15):
        now = datetime.now()
        slot = now.strftime("%Y-%m-%d %H:%M")
        if slot == last_slot:
            continue
        last_slot = slot
        try:
            if run_cron and _should_fire(run_cron, now):
                print(f"[scheduler] firing run @ {slot}")
                threading.Thread(target=run_stage, kwargs={"stage": "run", "limit": limit}, daemon=True).start()
            if inbox_cron and _should_fire(inbox_cron, now):
                print(f"[scheduler] firing inbox @ {slot}")
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
