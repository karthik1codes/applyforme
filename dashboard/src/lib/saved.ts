import { db } from "@/lib/db";

const SCHEMA = `CREATE TABLE IF NOT EXISTS saved_jobs (
  job_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);`;

export function ensureSaved() {
  db().exec(SCHEMA);
}

export function listSavedIds(): string[] {
  ensureSaved();
  return (db().prepare("SELECT job_id FROM saved_jobs ORDER BY created_at DESC").all() as { job_id: string }[]).map(
    (r) => r.job_id,
  );
}

export function isSaved(jobId: string): boolean {
  ensureSaved();
  return !!(db().prepare("SELECT 1 FROM saved_jobs WHERE job_id=?").get(jobId));
}

export function toggleSaved(jobId: string): boolean {
  ensureSaved();
  if (isSaved(jobId)) {
    db().prepare("DELETE FROM saved_jobs WHERE job_id=?").run(jobId);
    return false;
  }
  db().prepare("INSERT INTO saved_jobs (job_id, created_at) VALUES (?, ?)").run(jobId, new Date().toISOString());
  return true;
}
