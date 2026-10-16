from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

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
  applied_at TEXT
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
"""

MIGRATIONS = ["ALTER TABLE jobs ADD COLUMN category TEXT", "ALTER TABLE jobs ADD COLUMN applied_at TEXT"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self) -> None:
        self.db = sqlite3.connect(DATA_DIR / "applyforme.db", timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")  # dashboard reads while agents write
        self.db.executescript(SCHEMA)
        for m in MIGRATIONS:  # upgrade databases created by older versions
            try:
                self.db.execute(m)
            except sqlite3.OperationalError:
                pass
        for r in self.db.execute("SELECT id, title FROM jobs WHERE category IS NULL").fetchall():
            self.db.execute("UPDATE jobs SET category=? WHERE id=?", (categorize(r["title"]), r["id"]))
        self.db.commit()

    # ---- jobs -------------------------------------------------------------
    def add_job(self, job: Job) -> bool:
        """Insert if unseen. Returns True if new."""
        cur = self.db.execute(
            "INSERT OR IGNORE INTO jobs (id, company, title, location, url, job_json, status, updated_at, category)"
            " VALUES (?,?,?,?,?,?, 'new', ?, ?)",
            (job.id, job.company, job.title, job.location, job.url, job.model_dump_json(), _now(), categorize(job.title)),
        )
        self.db.commit()
        return cur.rowcount == 1

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
