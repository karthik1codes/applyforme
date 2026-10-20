from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from .categories import categorize
from .config import DATA_DIR
from .models import Job

# status: new -> matched -> skipped | ready -> needs_feedback -> ready -> applied | failed
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  company TEXT, title TEXT, location TEXT, url TEXT,
  job_json TEXT,
  score INTEGER,
  reasons TEXT,
  status TEXT DEFAULT 'new',
  cover_letter TEXT,
  notes TEXT,
  updated_at TEXT,
  category TEXT,
  applied_at TEXT,
  last_seen_at TEXT,
  dedupe_key TEXT
);
-- Questions the applier could not answer. The dashboard (or CLI) fills in `answer`.
CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  label TEXT NOT NULL,
  type TEXT, options TEXT, suggested TEXT,
  answer TEXT,
  created_at TEXT,
  UNIQUE(job_id, label)
);
-- Per-application timeline: submitted, confirmation / reply emails, etc.
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT, body TEXT,
  ref TEXT,
  created_at TEXT,
  UNIQUE(job_id, ref)
);
-- Small key/value store for dashboard settings (WhatsApp link, billing state).
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
-- Persistent state for one application attempt (see applyforme/apply_state.py).
CREATE TABLE IF NOT EXISTS apply_sessions (
  job_id TEXT PRIMARY KEY,
  state TEXT NOT NULL DEFAULT 'IDLE',
  step_count INTEGER NOT NULL DEFAULT 0,
  state_attempts INTEGER NOT NULL DEFAULT 0,
  retry_count INTEGER NOT NULL DEFAULT 0,
  last_signature TEXT DEFAULT '',
  duplicate_signature_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT DEFAULT '',
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  submit_authorized_at TEXT,
  submit_authorized_by TEXT,
  submit_attempted_at TEXT,
  submitted_at TEXT,
  confirmation TEXT,
  lock_owner TEXT,
  lock_expires_at REAL,
  created_at TEXT,
  updated_at TEXT
);
-- Append-only transition log for diagnostics (never contains credentials).
CREATE TABLE IF NOT EXISTS apply_steps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  state TEXT NOT NULL,
  result TEXT,
  detail TEXT,
  signature TEXT,
  created_at TEXT
);
-- Per-user LinkedIn OAuth connections (tokens are encrypted by the dashboard).
CREATE TABLE IF NOT EXISTS linkedin_connections (
  user_id TEXT PRIMARY KEY,
  member_id TEXT,
  display_name TEXT,
  email TEXT,
  picture TEXT,
  scope TEXT,
  token_type TEXT,
  access_token_enc TEXT,
  refresh_token_enc TEXT,
  expires_at TEXT,
  connected_at TEXT,
  updated_at TEXT,
  last_error TEXT
);
CREATE TABLE IF NOT EXISTS linkedin_oauth_states (
  state_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  created_at TEXT,
  expires_at TEXT,
  consumed_at TEXT
);
"""

MIGRATIONS = [
    "ALTER TABLE jobs ADD COLUMN category TEXT",
    "ALTER TABLE jobs ADD COLUMN applied_at TEXT",
    "ALTER TABLE jobs ADD COLUMN last_seen_at TEXT",
    "ALTER TABLE jobs ADD COLUMN dedupe_key TEXT",
]

# Statuses that are safe to drop automatically: nothing the user has acted on.
PRUNABLE_STATUSES = ("new", "matched", "skipped")

# Keep the row with the most useful state when the same role appears on two boards.
_STATUS_PRIORITY = {
    "applied": 0,
    "ready": 1,
    "awaiting_review": 1,
    "in_progress": 1,
    "needs_feedback": 2,
    "manual": 2,
    "blocked": 2,
    "matched": 3,
    "skipped": 4,
    "new": 5,
    "cancelled": 6,
    "failed": 6,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dedupe_key(title: str, company: str) -> str:
    """Same role → same key across boards (case/punctuation insensitive)."""
    norm_title = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    norm_company = re.sub(r"[^a-z0-9]+", " ", (company or "").lower()).strip()
    if not norm_title or not norm_company:
        return ""
    return f"{norm_title}|{norm_company}"


_COMPANY_STOP_WORDS = {
    "pvt", "ltd", "private", "limited", "inc", "llc", "corp", "corporation",
    "co", "company", "group", "technologies", "technology", "solutions",
    "services", "systems", "global", "india",
}


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _company_words(company: str) -> list[str]:
    words = [w for w in re.sub(r"[^a-z0-9]+", " ", (company or "").lower()).split() if w]
    trimmed = [w for w in words if w not in _COMPANY_STOP_WORDS]
    return trimmed or words


def _company_match(a: str, b: str) -> bool:
    """'Cisco' ≈ 'Cisco Systems'; 'Cloudsek' ≈ 'Cloudsek Information Security'."""
    wa, wb = _company_words(a), _company_words(b)
    if not wa or not wb:
        return False
    if wa == wb:
        return True
    short, long = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    return len(short[0]) >= 3 and long[: len(short)] == short


def _seen_at(row: sqlite3.Row) -> str:
    return row["last_seen_at"] or row["updated_at"] or ""


class Store:
    def __init__(self, path=None) -> None:
        self.db = sqlite3.connect(path or DATA_DIR / "applyforme.db", timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")  # dashboard reads while agents write
        self.db.executescript(SCHEMA)
        for m in MIGRATIONS:  # upgrade databases created by older versions
            try:
                self.db.execute(m)
            except sqlite3.OperationalError:
                pass
        # Indexes live here (not in SCHEMA) because an old DB gains the columns above first.
        self.db.executescript(
            "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);"
            "CREATE INDEX IF NOT EXISTS idx_jobs_dedupe ON jobs(dedupe_key);"
            "CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen_at);"
        )
        for r in self.db.execute("SELECT id, title FROM jobs WHERE category IS NULL").fetchall():
            self.db.execute("UPDATE jobs SET category=? WHERE id=?", (categorize(r["title"]), r["id"]))
        # Backfill retention / dedupe metadata for rows from older versions.
        for r in self.db.execute(
            "SELECT id, title, company, updated_at, last_seen_at, dedupe_key FROM jobs"
            " WHERE last_seen_at IS NULL OR dedupe_key IS NULL"
        ).fetchall():
            self.db.execute(
                "UPDATE jobs SET last_seen_at=COALESCE(last_seen_at, updated_at), dedupe_key=COALESCE(dedupe_key, ?)"
                " WHERE id=?",
                (_dedupe_key(r["title"], r["company"]), r["id"]),
            )
        self.db.commit()

    # ---- jobs -------------------------------------------------------------
    def add_job(self, job: Job, *, category: str | None = None) -> bool:
        """Insert if unseen. Returns True if new.

        A role already stored under another board's id (same title + company) is
        the same opening: refresh its ``last_seen_at`` instead of inserting a
        duplicate. Every row with that key is touched so retention never drops a
        role that is still being advertised.
        """
        cat = category or categorize(job.title)
        now = _now()
        key = _dedupe_key(job.title, job.company)

        existing = self.db.execute("SELECT id FROM jobs WHERE id=?", (job.id,)).fetchone()
        if existing:
            self.db.execute(
                "UPDATE jobs SET last_seen_at=?, dedupe_key=COALESCE(dedupe_key, ?) WHERE id=?",
                (now, key, job.id),
            )
            self.db.commit()
            return False

        if key:
            dup = self.db.execute("SELECT 1 FROM jobs WHERE dedupe_key=? LIMIT 1", (key,)).fetchone()
            if dup:
                self.db.execute("UPDATE jobs SET last_seen_at=? WHERE dedupe_key=?", (now, key))
                self.db.commit()
                return False

        # Near-duplicate: same title, company written differently on another board.
        same = self.db.execute(
            "SELECT id, company FROM jobs WHERE title = ? COLLATE NOCASE", (job.title,)
        ).fetchall()
        matches = [r["id"] for r in same if _company_match(job.company, r["company"])]
        if matches:
            ph = ",".join("?" for _ in matches)
            self.db.execute(f"UPDATE jobs SET last_seen_at=? WHERE id IN ({ph})", (now, *matches))
            self.db.commit()
            return False

        cur = self.db.execute(
            "INSERT OR IGNORE INTO jobs"
            " (id, company, title, location, url, job_json, status, updated_at, category, last_seen_at, dedupe_key)"
            " VALUES (?,?,?,?,?,?, 'new', ?, ?, ?, ?)",
            (job.id, job.company, job.title, job.location, job.url, job.model_dump_json(), now, cat, now, key),
        )
        self.db.commit()
        return cur.rowcount == 1

    def dedupe_jobs(self, *, dry_run: bool = False) -> list[str]:
        """Remove cross-board duplicates, keeping the row with real user progress.

        Pass 1 groups by exact title + company. Pass 2 catches the same role when
        a board writes the company differently ("Kuku" vs "Kuku Fm").
        """
        doomed: list[str] = []

        rows = self.db.execute(
            "SELECT id, dedupe_key, status, score, last_seen_at, updated_at FROM jobs"
            " WHERE dedupe_key IS NOT NULL AND dedupe_key<>''"
        ).fetchall()
        groups: dict[str, list[sqlite3.Row]] = {}
        for r in rows:
            groups.setdefault(r["dedupe_key"], []).append(r)

        for group in groups.values():
            if len(group) < 2:
                continue
            # Newest first, then best progress/highest score (stable sort keeps the newest tie-break).
            group = sorted(group, key=_seen_at, reverse=True)
            group = sorted(group, key=lambda r: (_STATUS_PRIORITY.get(r["status"], 9), -(r["score"] or -1)))
            doomed.extend(r["id"] for r in group[1:] if r["status"] in PRUNABLE_STATUSES)

        if doomed and not dry_run:
            self.delete_jobs(doomed)

        # Pass 2: same normalized title, near-identical company name.
        rows = self.db.execute(
            "SELECT id, title, company, status, score, last_seen_at, updated_at FROM jobs"
        ).fetchall()
        by_title: dict[str, list[sqlite3.Row]] = {}
        for r in rows:
            key = _norm_title(r["title"])
            if key:
                by_title.setdefault(key, []).append(r)

        near: list[str] = []
        for group in by_title.values():
            if len(group) < 2:
                continue
            clusters: list[list[sqlite3.Row]] = []
            for r in group:
                for cluster in clusters:
                    if any(_company_match(r["company"], x["company"]) for x in cluster):
                        cluster.append(r)
                        break
                else:
                    clusters.append([r])
            for cluster in clusters:
                if len(cluster) < 2:
                    continue
                ordered = sorted(cluster, key=_seen_at, reverse=True)
                ordered = sorted(
                    ordered, key=lambda r: (_STATUS_PRIORITY.get(r["status"], 9), -(r["score"] or -1))
                )
                near.extend(r["id"] for r in ordered[1:] if r["status"] in PRUNABLE_STATUSES)

        if near and not dry_run:
            self.delete_jobs(near)

        return list(dict.fromkeys(doomed + near))

    def prune_stale(self, *, days: int | None = None, dry_run: bool = False) -> list[str]:
        """Drop old, never-touched listings so the boards only show current roles.

        Only ``new`` / ``matched`` / ``skipped`` rows are eligible: applications,
        tailored resumes, manual follow-ups and anything the user has handled are
        never removed. Set ``JOB_RETENTION_DAYS=0`` to disable.
        """
        if days is None:
            days = int(os.getenv("JOB_RETENTION_DAYS", "10"))
        if days <= 0:
            return []
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        ph = ",".join("?" for _ in PRUNABLE_STATUSES)
        rows = self.db.execute(
            f"SELECT id FROM jobs WHERE status IN ({ph})"
            f" AND COALESCE(last_seen_at, updated_at, '') < ? AND COALESCE(last_seen_at, updated_at, '') <> ''",
            (*PRUNABLE_STATUSES, cutoff),
        ).fetchall()
        doomed = [r["id"] for r in rows]
        if not doomed:
            return []
        if dry_run:
            return doomed
        self.delete_jobs(doomed)
        return doomed

    def delete_jobs(self, ids: list[str]) -> int:
        """Delete jobs and their dependent rows. Applied sessions are preserved."""
        ids = [i for i in dict.fromkeys(ids) if i]
        if not ids:
            return 0
        ph = ",".join("?" for _ in ids)
        self.db.execute(f"DELETE FROM questions WHERE job_id IN ({ph})", ids)
        self.db.execute(f"DELETE FROM events WHERE job_id IN ({ph})", ids)
        self.db.execute(f"DELETE FROM apply_steps WHERE job_id IN ({ph})", ids)
        self.db.execute(
            f"DELETE FROM apply_sessions WHERE job_id IN ({ph})"
            " AND (submitted_at IS NULL OR submitted_at='')",
            ids,
        )
        cur = self.db.execute(f"DELETE FROM jobs WHERE id IN ({ph})", ids)
        self.db.commit()
        return cur.rowcount


    def by_status(self, status: str, limit: int = 100) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM jobs WHERE status=? ORDER BY COALESCE(score,0) DESC LIMIT ?", (status, limit)
        ).fetchall()

    def get(self, job_id: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()

    def update(self, job_id: str, **fields) -> None:
        fields["updated_at"] = _now()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))
        self.db.commit()

    def stats(self) -> dict[str, int]:
        rows = self.db.execute("SELECT status, COUNT(*) c FROM jobs GROUP BY status").fetchall()
        return {r["status"]: r["c"] for r in rows}

    # ---- human-in-the-loop questions -------------------------------------
    def save_questions(self, job_id: str, qs: list[dict]) -> None:
        for q in qs:
            self.db.execute(
                "INSERT OR IGNORE INTO questions (job_id, label, type, options, suggested, created_at) VALUES (?,?,?,?,?,?)",
                (job_id, q["label"], q.get("type"), json.dumps(q.get("options", [])), q.get("suggested"), _now()),
            )
        self.db.commit()

    def get_answers(self, job_id: str) -> dict[str, str]:
        rows = self.db.execute("SELECT label, answer FROM questions WHERE job_id=? AND answer IS NOT NULL AND answer<>''", (job_id,)).fetchall()
        return {r["label"]: r["answer"] for r in rows}

    # ---- timeline ----------------------------------------------------------
    def add_event(self, job_id: str, kind: str, title: str, body: str = "", ref: str | None = None) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO events (job_id, kind, title, body, ref, created_at) VALUES (?,?,?,?,?,?)",
            (job_id, kind, title, body, ref or f"{kind}:{_now()}", _now()),
        )
        self.db.commit()

    # ---- settings ----------------------------------------------------------
    def kv_get(self, key: str) -> str | None:
        r = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None

    def kv_set(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO kv (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.db.commit()

    # ---- application state machine ---------------------------------------
    def apply_session(self, job_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM apply_sessions WHERE job_id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def save_apply_session(self, job_id: str, **fields) -> None:
        """Upsert only the supplied columns; never clobbers unrelated progress."""
        if not fields:
            return
        now = _now()
        self.db.execute(
            "INSERT OR IGNORE INTO apply_sessions (job_id, created_at, updated_at) VALUES (?,?,?)",
            (job_id, now, now),
        )
        fields["updated_at"] = now
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE apply_sessions SET {cols} WHERE job_id=?", (*fields.values(), job_id))
        self.db.commit()

    def add_apply_step(self, job_id: str, *, state: str, result: str = "", detail: str = "", signature: str = "") -> None:
        self.db.execute(
            "INSERT INTO apply_steps (job_id, state, result, detail, signature, created_at) VALUES (?,?,?,?,?,?)",
            (job_id, state, result, (detail or "")[:2000], (signature or "")[:500], _now()),
        )
        self.db.commit()

    def acquire_apply_lock(self, job_id: str, owner: str, *, ttl_sec: float = 900.0) -> bool:
        """Atomically claim one application. Returns False if another worker holds it."""
        import time as _time

        now = _time.time()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "INSERT OR IGNORE INTO apply_sessions (job_id, created_at, updated_at) VALUES (?,?,?)",
                (job_id, _now(), _now()),
            )
            row = self.db.execute(
                "SELECT lock_owner, lock_expires_at FROM apply_sessions WHERE job_id=?", (job_id,)
            ).fetchone()
            held = row and row["lock_owner"] and float(row["lock_expires_at"] or 0) > now
            if held and row["lock_owner"] != owner:
                self.db.rollback()
                return False
            self.db.execute(
                "UPDATE apply_sessions SET lock_owner=?, lock_expires_at=?, updated_at=? WHERE job_id=?",
                (owner, now + max(30.0, ttl_sec), _now(), job_id),
            )
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            raise

    def release_apply_lock(self, job_id: str, owner: str) -> None:
        self.db.execute(
            "UPDATE apply_sessions SET lock_owner=NULL, lock_expires_at=NULL, updated_at=? "
            "WHERE job_id=? AND (lock_owner=? OR lock_owner IS NULL)",
            (_now(), job_id, owner),
        )
        self.db.commit()

    def request_apply_cancel(self, job_id: str) -> None:
        self.save_apply_session(job_id, cancel_requested=1)
        self.add_event(job_id, "cancel_requested", "Application cancellation requested", "")

    def clear_apply_cancel(self, job_id: str) -> None:
        self.save_apply_session(job_id, cancel_requested=0)

    def is_apply_cancelled(self, job_id: str) -> bool:
        row = self.db.execute("SELECT cancel_requested FROM apply_sessions WHERE job_id=?", (job_id,)).fetchone()
        return bool(row and row["cancel_requested"])

    def authorize_apply(self, job_id: str, by: str = "dashboard") -> None:
        """Record explicit user authorization to submit THIS job once."""
        self.save_apply_session(job_id, submit_authorized_at=_now(), submit_authorized_by=by)
        self.add_event(job_id, "submit_authorized", "You authorized submission", by)

    def clear_apply_authorization(self, job_id: str) -> None:
        """One authorization covers one submit attempt, never a later retry."""
        self.save_apply_session(job_id, submit_authorized_at=None, submit_authorized_by=None)

    def apply_submit_authorized(self, job_id: str, after: str | None = None) -> bool:
        """Whether this job has an explicit, unconsumed submit authorization.

        ``after`` is a per-attempt floor.  A plain prepare run passes its start
        time so an authorization left over from an older run cannot silently
        submit; a dashboard Submit click that arrives while the prepare browser
        is waiting is newer and is honoured.
        """
        row = self.db.execute(
            "SELECT submit_authorized_at, submitted_at FROM apply_sessions WHERE job_id=?", (job_id,)
        ).fetchone()
        if not row or not row["submit_authorized_at"] or row["submitted_at"]:
            return False
        if not after:
            return True
        try:
            authorized = datetime.fromisoformat(str(row["submit_authorized_at"]).replace("Z", "+00:00"))
            floor = datetime.fromisoformat(str(after).replace("Z", "+00:00"))
        except ValueError:
            return False
        return authorized >= floor

    def record_submission_attempt(self, job_id: str) -> bool:
        """Idempotency guard. Returns False if an attempt was already recorded."""
        now = _now()
        cur = self.db.execute(
            "UPDATE apply_sessions SET submit_attempted_at=?, updated_at=? "
            "WHERE job_id=? AND (submit_attempted_at IS NULL OR submit_attempted_at='')",
            (now, now, job_id),
        )
        self.db.commit()
        return cur.rowcount == 1

    def clear_submission_attempt(self, job_id: str) -> None:
        """Clear the idempotency marker after a submit that definitely did not send.

        Only used for a validation failure (the site rejected the form), never
        for an unverified click.
        """
        self.save_apply_session(job_id, submit_attempted_at=None)

    def record_submission_confirmed(self, job_id: str, note: str = "") -> None:
        now = _now()
        self.save_apply_session(
            job_id, submitted_at=now, confirmation=(note or "")[:1000],
            submit_authorized_at=None, submit_authorized_by=None,
        )
        self.add_event(job_id, "submitted", "Application confirmed", note or "confirmation detected", ref=f"submitted:{job_id}")

    def submission_recorded(self, job_id: str) -> bool:
        """True when a confirmed submission exists for this job (any source)."""
        row = self.db.execute(
            "SELECT submitted_at FROM apply_sessions WHERE job_id=?", (job_id,)
        ).fetchone()
        if row and row["submitted_at"]:
            return True
        job = self.db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if job and job["status"] == "applied":
            return True
        ev = self.db.execute(
            "SELECT 1 FROM events WHERE job_id=? AND kind='submitted' LIMIT 1", (job_id,)
        ).fetchone()
        return bool(ev)
