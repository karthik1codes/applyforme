import fs from "node:fs";
import path from "node:path";
import { db } from "@/lib/db";

const ROOT = path.resolve(process.cwd(), "..");
export const UPLOADS_DIR = path.join(ROOT, "data", "uploads");

const USERS_SCHEMA = `
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  name TEXT,
  image TEXT,
  resume_path TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
`;

export function ensureUsersTable() {
  db().exec(USERS_SCHEMA);
}

export type UserRow = {
  id: string;
  email: string;
  name: string | null;
  image: string | null;
  resume_path: string | null;
  created_at: string;
  updated_at: string;
};

export function upsertUser(u: { id: string; email: string; name?: string | null; image?: string | null }) {
  ensureUsersTable();
  const now = new Date().toISOString();
  db()
    .prepare(
      `INSERT INTO users (id, email, name, image, created_at, updated_at)
       VALUES (@id, @email, @name, @image, @now, @now)
       ON CONFLICT(id) DO UPDATE SET
         email=excluded.email, name=excluded.name, image=excluded.image, updated_at=excluded.updated_at`,
    )
    .run({ id: u.id, email: u.email, name: u.name ?? null, image: u.image ?? null, now });
}

export function getUser(id: string): UserRow | null {
  ensureUsersTable();
  return (db().prepare("SELECT * FROM users WHERE id=?").get(id) as UserRow | undefined) ?? null;
}

export function setUserResume(userId: string, resumePath: string) {
  ensureUsersTable();
  db().prepare("UPDATE users SET resume_path=?, updated_at=? WHERE id=?").run(resumePath, new Date().toISOString(), userId);
}

/** Save an uploaded resume for a signed-in user and sync it to the agent profile path. */
export function saveResume(userId: string, fileName: string, bytes: Buffer): { path: string; publicName: string } {
  const ext = path.extname(fileName).toLowerCase() || ".pdf";
  if (![".pdf", ".txt", ".doc", ".docx"].includes(ext)) {
    throw new Error("Upload a PDF or text resume (.pdf, .txt, .doc, .docx)");
  }
  if (bytes.length > 8 * 1024 * 1024) throw new Error("Resume must be under 8 MB");

  const dir = path.join(UPLOADS_DIR, userId.replace(/[^a-zA-Z0-9_-]/g, "_"));
  fs.mkdirSync(dir, { recursive: true });
  const dest = path.join(dir, `resume${ext}`);
  fs.writeFileSync(dest, bytes);

  // Agents read ./resume.pdf from the repo root — keep a copy there for the local pipeline.
  const agentCopy = path.join(ROOT, ext === ".pdf" ? "resume.pdf" : `resume${ext}`);
  fs.copyFileSync(dest, agentCopy);

  // Point profile.yaml at the agent copy when present.
  const profilePath = path.join(ROOT, "profile.yaml");
  if (fs.existsSync(profilePath)) {
    let yaml = fs.readFileSync(profilePath, "utf8");
    if (/^resume_path:/m.test(yaml)) {
      yaml = yaml.replace(/^resume_path:\s*.+$/m, `resume_path: ./${path.basename(agentCopy)}`);
    } else {
      yaml = `resume_path: ./${path.basename(agentCopy)}\n` + yaml;
    }
    fs.writeFileSync(profilePath, yaml, "utf8");
  }

  setUserResume(userId, dest);
  return { path: dest, publicName: path.basename(agentCopy) };
}

export function userHasResume(userId: string): boolean {
  const u = getUser(userId);
  return !!(u?.resume_path && fs.existsSync(u.resume_path));
}
