import { NextResponse } from "next/server";
import { getPipelineStatus, laneForStage, listRunningPipelines, startPipeline } from "@/lib/pipeline-runner";
import { auth, authDisabled } from "@/auth";

/**
 * Frontend + EventBridge entrypoint.
 * Auth: Bearer PIPELINE_WEBHOOK_SECRET, or a signed-in session (dashboard buttons).
 * Jobs and internships use separate lanes and can run in parallel.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function authorized(req: Request): Promise<boolean> {
  const secret = process.env.PIPELINE_WEBHOOK_SECRET || "";
  const authz = req.headers.get("authorization") || "";
  if (secret && authz === `Bearer ${secret}`) return true;
  if (secret && req.headers.get("x-pipeline-secret") === secret) return true;
  if (authDisabled()) return true;
  const session = await auth();
  return !!session?.user;
}

export async function GET() {
  return NextResponse.json({
    proxy: "ok",
    running: listRunningPipelines(),
    lanes: {
      jobs: getPipelineStatus("jobs"),
      internships: getPipelineStatus("internships"),
      apply: getPipelineStatus("apply"),
      inbox: getPipelineStatus("inbox"),
    },
  });
}

export async function POST(req: Request) {
  if (!(await authorized(req))) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  let body: { stage?: string; limit?: number; job_id?: string; jobId?: string } = {};
  try {
    body = (await req.json()) as typeof body;
  } catch {
    body = {};
  }
  const stage = (body.stage || "run").replace(/[^a-z]/g, "");
  const jobId = body.job_id || body.jobId;
  const lane = laneForStage(stage);
  const result = await startPipeline(stage, body.limit ?? 40, jobId ? { jobId } : undefined);
  return NextResponse.json(
    { accepted: result.ok, stage, lane, message: result.message, pipeline: getPipelineStatus(lane) },
    { status: result.ok ? 202 : 409 },
  );
}
