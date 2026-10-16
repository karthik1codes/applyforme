"use server";

const WORKER = () => (process.env.PIPELINE_WORKER_URL || "http://127.0.0.1:8787").replace(/\/$/, "");

export type TriggerResult = { ok: boolean; message: string; status?: number };

/** Server-side trigger — uses PIPELINE_WEBHOOK_SECRET from .env so users never paste it. */
export async function triggerPipeline(stage: string, limit = 40): Promise<TriggerResult> {
  const secret = process.env.PIPELINE_WEBHOOK_SECRET;
  if (!secret) {
    return {
      ok: false,
      message: "Automation isn’t configured yet. On the server, set PIPELINE_WEBHOOK_SECRET and start the worker.",
    };
  }
  const allowed = new Set(["run", "discover", "enrich", "match", "tailor", "inbox"]);
  if (!allowed.has(stage)) return { ok: false, message: "Unknown action." };

  try {
    const r = await fetch(`${WORKER()}/hooks/${stage}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${secret}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ limit, async: true }),
    });
    const data = (await r.json().catch(() => ({}))) as { error?: string; accepted?: boolean; stage?: string };
    if (r.status === 202 || r.ok) {
      return {
        ok: true,
        status: r.status,
        message:
          stage === "run"
            ? "Searching for jobs that match your profile. Check Jobs in a few minutes."
            : `Started “${stage}”. This finishes in the background.`,
      };
    }
    if (r.status === 409) {
      return { ok: false, status: 409, message: "A search is already running — try again shortly." };
    }
    return {
      ok: false,
      status: r.status,
      message: data.error || "Couldn’t reach the job worker. Is it running on this server?",
    };
  } catch {
    return {
      ok: false,
      message: "Worker offline. On EC2 run: sudo systemctl start applyforme-worker",
    };
  }
}

export async function workerHealth(): Promise<{ online: boolean; detail: string }> {
  try {
    const r = await fetch(`${WORKER()}/health`, { cache: "no-store" });
    const body = (await r.json()) as { status?: string; running?: unknown };
    return {
      online: r.ok,
      detail: body.running ? "Busy — a job search is in progress" : "Ready — automatic searches are on",
    };
  } catch {
    return { online: false, detail: "Worker offline — automatic searches won’t run until it’s started" };
  }
}
