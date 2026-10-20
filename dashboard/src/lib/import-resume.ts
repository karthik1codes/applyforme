/**
 * After a resume upload, parse the PDF into profile.yaml so Tailor can
 * generate job-specific PDFs and Profile fields auto-fill from the resume.
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");

function pythonBin(): string {
  const win = process.platform === "win32";
  const candidates = [
    process.env.APPLYFORME_PYTHON,
    path.join(ROOT, ".venv", win ? "Scripts\\python.exe" : "bin/python"),
    path.join(ROOT, "venv", win ? "Scripts\\python.exe" : "bin/python"),
    win ? "python" : "python3",
  ].filter(Boolean) as string[];
  for (const c of candidates) {
    if (c === "python" || c === "python3") return c;
    if (fs.existsSync(c)) return c;
  }
  return win ? "python" : "python3";
}

export type ImportResumeResult = {
  ok: boolean;
  roles?: number;
  skills?: number;
  education?: number;
  projects?: number;
  honors?: number;
  message: string;
};

/** Run `python -m applyforme import-resume` synchronously (blocks until done). */
export function importResumeIntoProfile(resumePath?: string): ImportResumeResult {
  const py = pythonBin();
  const args = ["-m", "applyforme", "import-resume"];
  if (resumePath) args.push("--path", resumePath);

  // The Python package lives outside the Next.js project; tracing it would
  // bundle the entire repo into the server output.
  const r = spawnSync(/* turbopackIgnore: true */ py, args, {
    cwd: ROOT,
    encoding: "utf8",
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
    timeout: 180_000,
  });

  const out = `${r.stdout || ""}\n${r.stderr || ""}`.trim();
  if (r.error) {
    return { ok: false, message: r.error.message };
  }
  if (r.status !== 0) {
    const hint = out.split("\n").filter(Boolean).slice(-3).join(" ") || `exit ${r.status}`;
    return { ok: false, message: hint };
  }

  const pick = (re: RegExp) => Number((out.match(re) || [])[1] || 0);
  return {
    ok: true,
    roles: pick(/(\d+)\s+roles/),
    skills: pick(/(\d+)\s+skills/),
    education: pick(/(\d+)\s+education/),
    projects: pick(/(\d+)\s+projects/),
    honors: pick(/(\d+)\s+honors/),
    message: out || "Imported into profile.yaml",
  };
}
