import fs from "node:fs";
import path from "node:path";
import Database from "better-sqlite3";

/** Same SQLite file the Python agents write to (see applyforme/store.py). */
const ROOT = path.resolve(process.cwd(), "..");
const DB_PATH = process.env.APPLYFORME_DB ?? path.join(ROOT, "data", "applyforme.db");
export const OUTPUT_DIR = process.env.APPLYFORME_OUTPUT ?? path.join(ROOT, "output");
export const PROFILE_PATH = path.join(ROOT, "profile.yaml");

export const STATUSES = ["new", "matched", "skipped", "ready", "needs_feedback", "manual", "applied", "failed"] as const;
export type Status = (typeof STATUSES)[number];

// Keep in sync with applyforme/store.py (both sides use CREATE IF NOT EXISTS).
const SCHEMA = `
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, company TEXT, title TEXT, location TEXT, url TEXT, job_json TEXT,
  score INTEGER, reasons TEXT, status TEXT DEFAULT 'new', cover_letter TEXT, notes TEXT,
  updated_at TEXT, category TEXT, applied_at TEXT
);
CREATE TABLE IF NOT EXISTS questions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, label TEXT NOT NULL,
  type TEXT, options TEXT, suggested TEXT, answer TEXT, created_at TEXT, UNIQUE(job_id, label)
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, kind TEXT NOT NULL,
  title TEXT, body TEXT, ref TEXT, created_at TEXT, UNIQUE(job_id, ref)
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
`;

const g = globalThis as unknown as { __afmDb?: Database.Database };

export function db(): Database.Database {
  if (!g.__afmDb) {
    fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });
    const d = new Database(DB_PATH, { timeout: 15000 });
    d.pragma("journal_mode = WAL");
    d.exec(SCHEMA);
    const cols = (d.pragma("table_info(jobs)") as { name: string }[]).map((c) => c.name);
    if (!cols.includes("category")) d.exec("ALTER TABLE jobs ADD COLUMN category TEXT");
    if (!cols.includes("applied_at")) d.exec("ALTER TABLE jobs ADD COLUMN applied_at TEXT");
    g.__afmDb = d;
  }
  return g.__afmDb;
}

// ---------------------------------------------------------------- types ----
type JobRow = {
  id: string; company: string; title: string; location: string; url: string; job_json: string | null;
  score: number | null; reasons: string | null; status: Status; cover_letter: string | null;
  notes: string | null; updated_at: string; category: string | null; applied_at: string | null;
};

export type Job = {
  id: string; company: string; title: string; location: string; url: string;
  score: number | null; status: Status; category: string; notes: string | null;
  updatedAt: string; appliedAt: string | null;
  reasons: string[]; redFlags: string[];
  coverLetter: string; resumePdf: string | null; resumeTex: string | null;
};

export type Question = {
  id: number; jobId: string; label: string; type: string; options: string[];
  suggested: string | null; answer: string | null;
};

export type AppEvent = {
  id: number; jobId: string; kind: string; title: string; body: string; createdAt: string;
  company?: string; jobTitle?: string;
};

const base = (p?: string | null) => (p ? p.split(/[\\/]/).pop() || null : null);
const json = <T>(s: string | null | undefined, fallback: T): T => {
  try { return s ? (JSON.parse(s) as T) : fallback; } catch { return fallback; }
};

function mapJob(r: JobRow): Job {
  const why = json<{ reasons?: string[]; red_flags?: string[] }>(r.reasons, {});
  const t = json<{ cover_letter?: string; resume_pdf?: string; resume_tex?: string }>(r.cover_letter, {});
  return {
    id: r.id, company: r.company, title: r.title, location: r.location ?? "", url: r.url,
    score: r.score, status: r.status, category: r.category ?? "Other", notes: r.notes,
    updatedAt: r.updated_at, appliedAt: r.applied_at,
    reasons: why.reasons ?? [], redFlags: why.red_flags ?? [],
    coverLetter: t.cover_letter ?? "", resumePdf: base(t.resume_pdf), resumeTex: base(t.resume_tex),
  };
}

// -------------------------------------------------------------- queries ----
export function listJobs(opts: { status?: Status | Status[]; limit?: number; order?: "recent" | "score" } = {}): Job[] {
  const st = opts.status ? (Array.isArray(opts.status) ? opts.status : [opts.status]) : [];
  const where = st.length ? `WHERE status IN (${st.map(() => "?").join(",")})` : "";
  const order = opts.order === "score" ? "COALESCE(score,0) DESC, updated_at DESC" : "COALESCE(applied_at, updated_at) DESC";
  const rows = db().prepare(`SELECT * FROM jobs ${where} ORDER BY ${order} LIMIT ?`).all(...st, opts.limit ?? 200) as JobRow[];
  return rows.map(mapJob);
}

export function getJob(id: string): (Job & { description: string }) | null {
  const r = db().prepare("SELECT * FROM jobs WHERE id=?").get(id) as JobRow | undefined;
  if (!r) return null;
  return { ...mapJob(r), description: json<{ description?: string }>(r.job_json, {}).description ?? "" };
}

export function statusCounts(): Record<string, number> {
  const rows = db().prepare("SELECT status, COUNT(*) c FROM jobs GROUP BY status").all() as { status: string; c: number }[];
  return Object.fromEntries(rows.map((r) => [r.status, r.c]));
}

export function overview() {
  const counts = statusCounts();
  const d = db();
  const one = (sql: string, ...a: unknown[]) => (d.prepare(sql).get(...a) as { n: number }).n;
  const since = (days: number) => new Date(Date.now() - days * 864e5).toISOString();
  return {
    counts,
    total: Object.values(counts).reduce((a, b) => a + b, 0),
    applied: counts.applied ?? 0,
    appliedWeek: one("SELECT COUNT(*) n FROM jobs WHERE status='applied' AND applied_at>=?", since(7)),
    appliedToday: one("SELECT COUNT(*) n FROM jobs WHERE status='applied' AND applied_at>=?", since(1)),
    needsFeedback: counts.needs_feedback ?? 0,
    ready: counts.ready ?? 0,
    avgScore: Math.round(one("SELECT COALESCE(AVG(score),0) n FROM jobs WHERE score IS NOT NULL")),
    replies: one("SELECT COUNT(*) n FROM events WHERE kind IN ('reply','interview','confirmation','rejection')"),
  };
}

/** Per-day counts for the area chart: applications submitted vs. jobs shortlisted (ready/applied/...). */
export function dailySeries(days = 90) {
  const out = new Map<string, { date: string; applied: number; shortlisted: number }>();
  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(Date.now() - i * 864e5).toISOString().slice(0, 10);
    out.set(date, { date, applied: 0, shortlisted: 0 });
  }
  const bump = (sql: string, key: "applied" | "shortlisted") => {
    for (const r of db().prepare(sql).all() as { d: string; n: number }[]) {
      const row = out.get(r.d);
      if (row) row[key] += r.n;
    }
  };
  bump("SELECT substr(applied_at,1,10) d, COUNT(*) n FROM jobs WHERE applied_at IS NOT NULL GROUP BY d", "applied");
  bump("SELECT substr(updated_at,1,10) d, COUNT(*) n FROM jobs WHERE status IN ('ready','needs_feedback','manual','applied','matched') GROUP BY d", "shortlisted");
  return [...out.values()];
}

export function questionsFor(jobId: string): Question[] {
  const rows = db().prepare("SELECT * FROM questions WHERE job_id=? ORDER BY id").all(jobId) as {
    id: number; job_id: string; label: string; type: string; options: string; suggested: string | null; answer: string | null;
  }[];
  return rows.map((r) => ({
    id: r.id, jobId: r.job_id, label: r.label, type: r.type ?? "text",
    options: json<string[]>(r.options, []), suggested: r.suggested, answer: r.answer,
  }));
}

export function feedbackQueue() {
  return listJobs({ status: "needs_feedback", order: "recent" }).map((job) => ({ job, questions: questionsFor(job.id) }));
}

export function jobEvents(jobId: string): AppEvent[] {
  return (db().prepare("SELECT * FROM events WHERE job_id=? ORDER BY created_at DESC, id DESC").all(jobId) as EventRow[]).map(mapEvent);
}

type EventRow = { id: number; job_id: string; kind: string; title: string; body: string; created_at: string; company?: string; jtitle?: string };
const mapEvent = (r: EventRow): AppEvent => ({
  id: r.id, jobId: r.job_id, kind: r.kind, title: r.title ?? "", body: r.body ?? "",
  createdAt: r.created_at, company: r.company, jobTitle: r.jtitle,
});

/** Applied inbox: everything that happened after you applied (submitted, employer replies, interviews...). */
export function inbox(kind?: string): AppEvent[] {
  const rows = db()
    .prepare(
      `SELECT e.*, j.company, j.title AS jtitle FROM events e JOIN jobs j ON j.id = e.job_id
       WHERE e.kind <> 'needs_feedback' AND e.kind <> 'answered' ${kind ? "AND e.kind = ?" : ""}
       ORDER BY e.created_at DESC, e.id DESC LIMIT 300`,
    )
    .all(...(kind ? [kind] : [])) as EventRow[];
  return rows.map(mapEvent);
}

export function inboxCounts(): Record<string, number> {
  const rows = db().prepare("SELECT kind, COUNT(*) c FROM events WHERE kind NOT IN ('needs_feedback','answered') GROUP BY kind").all() as { kind: string; c: number }[];
  return Object.fromEntries(rows.map((r) => [r.kind, r.c]));
}

/** Resumes grouped by job category (only jobs that already have a tailored resume). */
export function resumesByCategory(): Record<string, Job[]> {
  const jobs = listJobs({ limit: 500, order: "score" }).filter((j) => j.resumePdf || j.resumeTex);
  const groups: Record<string, Job[]> = {};
  for (const j of jobs) (groups[j.category] ??= []).push(j);
  return groups;
}

export function addEvent(jobId: string, kind: string, title: string, body = "") {
  db().prepare("INSERT OR IGNORE INTO events (job_id, kind, title, body, ref, created_at) VALUES (?,?,?,?,?,?)")
    .run(jobId, kind, title, body, `${kind}:${Date.now()}`, new Date().toISOString());
}

export function kvGet<T>(key: string, fallback: T): T {
  const r = db().prepare("SELECT value FROM kv WHERE key=?").get(key) as { value: string } | undefined;
  return json<T>(r?.value, fallback);
}

export function kvSet(key: string, value: unknown) {
  db().prepare("INSERT INTO kv (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").run(key, JSON.stringify(value));
}
