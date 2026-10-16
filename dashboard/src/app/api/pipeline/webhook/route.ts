import { NextResponse } from "next/server";

/**
 * Public entrypoint for EventBridge / external cron → worker on the same EC2 box.
 *
 *   POST /api/pipeline/webhook
 *   Authorization: Bearer $PIPELINE_WEBHOOK_SECRET
 *   Body: { "stage": "run"|"discover"|"match"|"tailor"|"inbox"|"apply", "limit"?: 40, "async"?: true }
 *
 * Forwards to PIPELINE_WORKER_URL (default http://127.0.0.1:8787/hooks/<stage>).
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const WORKER = () => (process.env.PIPELINE_WORKER_URL || "http://127.0.0.1:8787").replace(/\/$/, "");

function authorized(req: Request): boolean {
  const secret = process.env.PIPELINE_WEBHOOK_SECRET || "";
  if (!secret) return false;
  const auth = req.headers.get("authorization") || "";
  if (auth === `Bearer ${secret}`) return true;
  return req.headers.get("x-pipeline-secret") === secret;
}

export async function GET() {
  try {
    const r = await fetch(`${WORKER()}/health`, { cache: "no-store" });
    const body = await r.json();
    return NextResponse.json({ proxy: "ok", worker: body });
  } catch (e) {
    return NextResponse.json(
      { proxy: "ok", worker: null, error: e instanceof Error ? e.message : "worker unreachable" },
      { status: 503 },
    );
  }
}

export async function POST(req: Request) {
  if (!process.env.PIPELINE_WEBHOOK_SECRET) {
    return NextResponse.json({ error: "PIPELINE_WEBHOOK_SECRET not configured" }, { status: 503 });
  }
  if (!authorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  let body: { stage?: string; limit?: number; async?: boolean } = {};
  try {
    body = (await req.json()) as typeof body;
  } catch {
    body = {};
  }
  const stage = (body.stage || "run").replace(/[^a-z]/g, "");
  const allowed = new Set(["run", "discover", "enrich", "match", "tailor", "inbox", "apply"]);
  if (!allowed.has(stage)) {
    return NextResponse.json({ error: `unknown stage`, allowed: [...allowed] }, { status: 400 });
  }

  const secret = process.env.PIPELINE_WEBHOOK_SECRET!;
  try {
    const r = await fetch(`${WORKER()}/hooks/${stage}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${secret}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ limit: body.limit, async: body.async ?? true }),
    });
    const data = await r.json().catch(() => ({}));
    return NextResponse.json(data, { status: r.status });
  } catch (e) {
    return NextResponse.json(
      { error: "worker unreachable — is `python -m applyforme serve` running?", detail: e instanceof Error ? e.message : String(e) },
      { status: 502 },
    );
  }
}
