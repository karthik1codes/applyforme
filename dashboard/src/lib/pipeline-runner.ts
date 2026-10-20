/**
 * Run pipeline stages from the Next.js server — no SSH, no separate terminal.
 * Jobs and internships use separate lanes so they can run in parallel.
 */
import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { db } from "@/lib/db";
import { buildPipelineArgs, type StartOptions } from "@/lib/pipeline-args";
import { laneForStage, type PipelineLane } from "@/lib/pipeline-lanes";

export type { StartOptions } from "@/lib/pipeline-args";

export type { PipelineLane } from "@/lib/pipeline-lanes";
export { laneForStage } from "@/lib/pipeline-lanes";

const ROOT = path.resolve(process.cwd(), "..");
const WORKER = () => (process.env.PIPELINE_WORKER_URL || "http://127.0.0.1:8787").replace(/\/$/, "");

export type PipelineStatus = {
  lane: PipelineLane;
  stage: string | null;
  state: "idle" | "running" | "ok" | "error";
  startedAt: string | null;
  finishedAt: string | null;
  message: string;
  pid?: number;
};

const IDLE = (lane: PipelineLane): PipelineStatus => ({
  lane,
  stage: null,
  state: "idle",
  startedAt: null,
  finishedAt: null,
  message: "Ready when you are.",
});

const g = globalThis as unknown as { __afmPipelineChildren?: Partial<Record<PipelineLane, ChildProcess | null>> };

function children(): Partial<Record<PipelineLane, ChildProcess | null>> {
  if (!g.__afmPipelineChildren) g.__afmPipelineChildren = {};
  return g.__afmPipelineChildren;
}

function statusKey(lane: PipelineLane): string {
  return `pipeline_status:${lane}`;
}

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

export function getPipelineStatus(lane: PipelineLane = "jobs"): PipelineStatus {
  try {
    const row = db().prepare("SELECT value FROM kv WHERE key=?").get(statusKey(lane)) as { value: string } | undefined;
    // Migrate legacy single key into jobs lane
    if (!row?.value && lane === "jobs") {
      const legacy = db().prepare("SELECT value FROM kv WHERE key='pipeline_status'").get() as { value: string } | undefined;
      if (legacy?.value) {
        const s = { ...JSON.parse(legacy.value), lane: "jobs" } as PipelineStatus;
        setPipelineStatus(s);
        return cleanStatus(s);
      }
    }
    if (row?.value) return cleanStatus({ ...JSON.parse(row.value), lane } as PipelineStatus);
  } catch {
    /* empty */
  }
  return IDLE(lane);
}

function cleanStatus(s: PipelineStatus): PipelineStatus {
  if (s.state === "error" && /UnicodeEncodeError|charmap|\[\d{1,2}m|Traceback/.test(s.message || "")) {
    resetPipelineStatus(s.lane);
    return IDLE(s.lane);
  }
  return s;
}

function setPipelineStatus(s: PipelineStatus) {
  db()
    .prepare("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value")
    .run(statusKey(s.lane), JSON.stringify(s));
}

export function resetPipelineStatus(lane: PipelineLane = "jobs") {
  setPipelineStatus(IDLE(lane));
}

export function listRunningPipelines(): PipelineStatus[] {
  return (["jobs", "internships", "apply", "inbox"] as PipelineLane[])
    .map((lane) => getPipelineStatus(lane))
    .filter((s) => s.state === "running");
}

async function workerUp(): Promise<boolean> {
  try {
    const r = await fetch(`${WORKER()}/health`, { cache: "no-store", signal: AbortSignal.timeout(1500) });
    return r.ok;
  } catch {
    return false;
  }
}

async function triggerWorker(stage: string, limit: number, opts?: StartOptions): Promise<boolean> {
  const secret = process.env.PIPELINE_WEBHOOK_SECRET;
  if (!secret) return false;
  if (!(await workerUp())) return false;
  const r = await fetch(`${WORKER()}/hooks/${stage}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      limit,
      async: true,
      lane: laneForStage(stage),
      ...(opts?.jobId ? { job_id: opts.jobId } : {}),
      ...(opts?.submit ? { submit: true } : {}),
    }),
  });
  return r.status === 202 || r.ok;
}

function stageMessage(stage: string, phase: "start" | "ok" | "fail", detail?: string): string {
  if (stage === "run") {
    if (phase === "start") return "Finding and scoring jobs for you…";
    if (phase === "ok") return "Done — open Jobs to see matches.";
  }
  if (stage === "internships") {
    if (phase === "start") return "Internship pipeline: Glassdoor, Wellfound, LinkedIn & more…";
    if (phase === "ok") return "Internship search done — open Internships.";
  }
  if (stage === "apply") {
    if (phase === "start") return "Opening Chromium — watch the live view on the application page…";
    if (phase === "ok") return "Apply step finished — check Applications for status.";
  }
  if (stage === "inbox") {
    if (phase === "start") return "Checking employer inbox…";
    if (phase === "ok") return "Inbox check finished.";
  }
  if (stage === "cleanup") {
    if (phase === "start") return "Removing stale and duplicate listings…";
    if (phase === "ok") return "Cleanup finished — boards are fresh.";
  }
  if (phase === "start") return `Running ${stage}…`;
  if (phase === "ok") return `${stage} finished.`;
  return detail || `Failed on ${stage}.`;
}

function spawnLocal(stage: string, limit: number, opts?: StartOptions): { ok: boolean; message: string; pid?: number } {
  const lane = laneForStage(stage);
  const slots = children();
  const existing = slots[lane];
  if (existing && !existing.killed && existing.exitCode === null) {
    return {
      ok: false,
      message:
        lane === "internships"
          ? "Internship search is already running — hang tight."
          : "That search is already running — hang tight.",
    };
  }

  const py = pythonBin();
  const args = buildPipelineArgs(stage, limit, opts);

  // Cursor sandbox sets PLAYWRIGHT_BROWSERS_PATH to a cache that often lacks
  // the Chromium build Playwright needs — drop it so Apply uses %LOCALAPPDATA%\ms-playwright.
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
    APPLYFORME_PIPELINE_LANE: lane,
  };
  const pwPath = env.PLAYWRIGHT_BROWSERS_PATH || "";
  if (/cursor-sandbox-cache|sandbox-cache/i.test(pwPath)) {
    delete env.PLAYWRIGHT_BROWSERS_PATH;
  }

  // The Python package lives outside the Next.js project; tracing it would
  // bundle the entire repo into the server output.
  const child = spawn(/* turbopackIgnore: true */ py, args, {
    cwd: ROOT,
    env,
    detached: false,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  slots[lane] = child;

  const startedAt = new Date().toISOString();
  setPipelineStatus({
    lane,
    stage,
    state: "running",
    startedAt,
    finishedAt: null,
    message: stageMessage(stage, "start"),
    pid: child.pid,
  });

  const scrub = (s: string) =>
    s
      .replace(/\x1b\[[0-9;]*m/g, "")
      .replace(/[^\x09\x0a\x0d\x20-\x7e]/g, " ")
      .replace(/\s+/g, " ")
      .trim();

  let errTail = "";
  child.stderr?.on("data", (b: Buffer) => {
    errTail = (errTail + b.toString("utf8")).slice(-4000);
  });
  child.stdout?.on("data", (b: Buffer) => {
    errTail = (errTail + b.toString("utf8")).slice(-4000);
  });
  child.on("close", (code) => {
    if (slots[lane] === child) slots[lane] = null;
    const hint = scrub(errTail).slice(-180);
    setPipelineStatus({
      lane,
      stage,
      state: code === 0 ? "ok" : "error",
      startedAt,
      finishedAt: new Date().toISOString(),
      message:
        code === 0
          ? stageMessage(stage, "ok")
          : stageMessage(stage, "fail", `Failed (${code}). ${hint || "Check server logs."}`),
      pid: child.pid,
    });
  });
  child.on("error", (e) => {
    if (slots[lane] === child) slots[lane] = null;
    setPipelineStatus({
      lane,
      stage,
      state: "error",
      startedAt,
      finishedAt: new Date().toISOString(),
      message: `Could not start Python (${e.message}). Is .venv installed?`,
    });
  });

  return {
    ok: true,
    message:
      stage === "run"
        ? "Jobs pipeline started. New roles will show up under Jobs shortly."
        : stage === "apply"
          ? "Applying in the background — watch the banner for progress."
          : stage === "internships"
            ? "Internship pipeline started — independent from Jobs. Results land under Internships."
            : stage === "tailor"
              ? "Tailoring in the background — wait until Apply unlocks and the resume appears below."
              : stage === "cleanup"
                ? "Cleanup started — stale and duplicate listings will be removed."
                : `Started ${stage} in the background.`,
    pid: child.pid,
  };
}

const ALLOWED = new Set(["run", "discover", "internships", "enrich", "match", "tailor", "inbox", "apply", "cleanup"]);

/** Start a pipeline stage on its own lane (jobs ∥ internships). */
export async function startPipeline(
  stage: string,
  limit = 40,
  opts?: StartOptions,
): Promise<{ ok: boolean; message: string }> {
  if (!ALLOWED.has(stage)) return { ok: false, message: "Unknown action." };
  const lane = laneForStage(stage);
  const cur = getPipelineStatus(lane);
  if (cur.state === "running") {
    return {
      ok: false,
      message:
        lane === "internships"
          ? "Internship pipeline is already running — hang tight."
          : "That pipeline is already running — hang tight.",
    };
  }

  try {
    if (await triggerWorker(stage, limit, opts)) {
      setPipelineStatus({
        lane,
        stage,
        state: "running",
        startedAt: new Date().toISOString(),
        finishedAt: null,
        message: stageMessage(stage, "start"),
      });
      return {
        ok: true,
        message:
          stage === "run"
            ? "Jobs search started."
            : stage === "internships"
              ? "Internship search started (separate pipeline)."
              : stage === "apply"
                ? "Application started — the form will open shortly."
                : `Started ${stage}.`,
      };
    }
  } catch {
    /* fall through to local spawn */
  }

  return spawnLocal(stage, limit, opts);
}
