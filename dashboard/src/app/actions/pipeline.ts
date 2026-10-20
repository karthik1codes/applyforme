"use server";

import { revalidatePath } from "next/cache";
import { auth, authDisabled } from "@/auth";
import {
  addEvent,
  authorizeApply,
  clearApplyAuthorization,
  clearApplyCancel,
  db,
  getApplySession,
  getJob,
  requestApplyCancel,
  submissionRecorded,
} from "@/lib/db";
import { sessionUserId } from "@/lib/onboarding-gate";
import {
  getPipelineStatus,
  listRunningPipelines,
  resetPipelineStatus,
  startPipeline,
  type PipelineLane,
  type PipelineStatus,
} from "@/lib/pipeline-runner";

export type TriggerResult = { ok: boolean; message: string; status?: number };

async function actor(): Promise<string | null> {
  if (authDisabled()) return "local";
  const session = await auth();
  return session?.user?.email ? sessionUserId(session) : null;
}

/** One click from the UI — runs agents via worker or local Python. No terminal. */
export async function triggerPipeline(stage: string, limit = 40, jobId?: string): Promise<TriggerResult> {
  const r = await startPipeline(stage, limit, jobId ? { jobId } : undefined);
  revalidatePath("/", "layout");
  return { ok: r.ok, message: r.message, status: r.ok ? 202 : 500 };
}

/**
 * Prepare an application: open the browser, fill and validate the form, then
 * stop for review.  This NEVER authorizes submission.
 */
export async function prepareApplication(jobId: string): Promise<TriggerResult> {
  const user = await actor();
  if (!user) return { ok: false, message: "Sign in first.", status: 401 };
  const job = getJob(jobId);
  if (!job) return { ok: false, message: "Job not found.", status: 404 };
  if (submissionRecorded(jobId) || job.status === "applied") {
    return { ok: false, message: "This application is already submitted." };
  }
  const session = getApplySession(jobId);
  if (session?.submitAttemptedAt) {
    return {
      ok: false,
      message: "A previous submit click was recorded but not confirmed. Check the site/email before retrying.",
    };
  }
  if (!job.coverLetter?.trim()) {
    return { ok: false, message: "Tailor the resume and cover letter first." };
  }
  // Defence in depth: a previous authorization must never leak into a new
  // prepare run and turn a review into a silent submit.  A stale cancellation
  // flag from an earlier run is cleared only by this explicit new prepare.
  clearApplyAuthorization(jobId);
  clearApplyCancel(jobId);
  db()
    .prepare("UPDATE jobs SET status='in_progress', notes=?, updated_at=? WHERE id=?")
    .run("Preparing the application — nothing is submitted until you approve.", new Date().toISOString(), jobId);
  addEvent(jobId, "preparing", "Preparing application", "The agent is filling the form for your review.");

  const r = await startPipeline("apply", 1, { jobId });
  if (!r.ok) {
    db()
      .prepare("UPDATE jobs SET status='ready', notes=?, updated_at=? WHERE id=?")
      .run(r.message.slice(0, 200), new Date().toISOString(), jobId);
    return { ok: false, message: r.message, status: 500 };
  }
  revalidatePath("/", "layout");
  return {
    ok: true,
    message: "Preparing — the form will stop for your review. Nothing is submitted automatically.",
    status: 202,
  };
}

/**
 * Explicitly authorize ONE submission for an application that is already
 * filled and awaiting review.  The authorization is one-shot and is consumed
 * by the applier.
 */
export async function submitApplication(jobId: string): Promise<TriggerResult> {
  const user = await actor();
  if (!user) return { ok: false, message: "Sign in first.", status: 401 };
  const job = getJob(jobId);
  if (!job) return { ok: false, message: "Job not found.", status: 404 };
  if (submissionRecorded(jobId) || job.status === "applied") {
    return { ok: false, message: "This application is already submitted." };
  }
  const session = getApplySession(jobId);
  const filled = job.status === "awaiting_review" || session?.state === "AWAITING_USER_REVIEW";
  if (!filled) {
    return { ok: false, message: "Prepare the form and review it before submitting." };
  }
  if (session?.submitAttemptedAt) {
    return {
      ok: false,
      message: "A previous submit click was recorded but not confirmed. Check the site/email before retrying.",
    };
  }
  if (!authorizeApply(jobId, user)) {
    return { ok: false, message: "Could not record your submit authorization. Nothing was sent." };
  }
  db()
    .prepare("UPDATE jobs SET status='in_progress', notes=?, updated_at=? WHERE id=?")
    .run("Submitting the application you reviewed.", new Date().toISOString(), jobId);
  addEvent(jobId, "submit_authorized", "You authorized this submission", "One application, one submit.");

  const lockLive = !!session?.lockExpiresAt && session.lockExpiresAt > Date.now() / 1000;
  const running = getPipelineStatus("apply").state === "running" || lockLive;
  if (running) {
    // The browser that prepared the form is still waiting on this row.
    revalidatePath("/", "layout");
    return { ok: true, message: "Authorized — the open browser will submit this one application now.", status: 202 };
  }

  const r = await startPipeline("apply", 1, { jobId, submit: true });
  if (!r.ok) {
    clearApplyAuthorization(jobId);
    db()
      .prepare("UPDATE jobs SET status='awaiting_review', notes=?, updated_at=? WHERE id=?")
      .run("Submit could not start — review the form and try again.", new Date().toISOString(), jobId);
    return { ok: false, message: r.message, status: 500 };
  }
  revalidatePath("/", "layout");
  return { ok: true, message: "Submitting this one application now.", status: 202 };
}

/** Stop the applier at its next safe boundary. Nothing is unsubmitted. */
export async function cancelApplication(jobId: string): Promise<TriggerResult> {
  const user = await actor();
  if (!user) return { ok: false, message: "Sign in first.", status: 401 };
  const job = getJob(jobId);
  if (!job) return { ok: false, message: "Job not found.", status: 404 };
  if (submissionRecorded(jobId) || job.status === "applied") {
    return { ok: false, message: "Already submitted — a submitted application cannot be cancelled." };
  }
  // Revoke any not-yet-consumed authorization as well as requesting the stop.
  // If the applier has already crossed the submit boundary this cannot undo
  // the click; the UI keeps that distinction explicit.
  clearApplyAuthorization(jobId);
  requestApplyCancel(jobId);
  db()
    .prepare("UPDATE jobs SET status='cancelled', notes=?, updated_at=? WHERE id=?")
    .run("Cancelled by you. Nothing was submitted.", new Date().toISOString(), jobId);
  addEvent(jobId, "cancelled", "Application cancelled", "Stopped before submission.");
  revalidatePath("/", "layout");
  return { ok: true, message: "Cancellation requested. The applier stops at the next safe step." };
}

/** Small polling payload for the review/cancel card. */
export async function applySessionState(jobId: string): Promise<{
  status: string;
  state: string | null;
  awaitingReview: boolean;
  submitted: boolean;
  cancelled: boolean;
  lastError: string;
  submitAttempted: boolean;
}> {
  const job = getJob(jobId);
  const session = getApplySession(jobId);
  return {
    status: job?.status ?? "missing",
    state: session?.state ?? null,
    awaitingReview: job?.status === "awaiting_review" || session?.state === "AWAITING_USER_REVIEW",
    submitted: submissionRecorded(jobId) || job?.status === "applied",
    cancelled: job?.status === "cancelled",
    lastError: session?.lastError ?? "",
    submitAttempted: !!session?.submitAttemptedAt,
  };
}

/** Poll whether a job has a tailored resume + cover letter (Apply unlocks). */
export async function jobTailorReady(jobId: string): Promise<{
  ready: boolean;
  status: string;
  hasCover: boolean;
  hasResumePdf: boolean;
}> {
  const job = getJob(jobId);
  if (!job) return { ready: false, status: "missing", hasCover: false, hasResumePdf: false };
  const hasCover = !!job.coverLetter?.trim();
  const hasResumePdf = !!job.resumePdf;
  return {
    ready: hasCover && (job.status === "ready" || job.status === "manual"),
    status: job.status,
    hasCover,
    hasResumePdf,
  };
}

export async function pipelineStatus(lane: PipelineLane = "jobs"): Promise<PipelineStatus> {
  return getPipelineStatus(lane);
}

export async function runningPipelines(): Promise<PipelineStatus[]> {
  return listRunningPipelines();
}

export async function clearPipelineStatus(lane: PipelineLane = "jobs"): Promise<void> {
  resetPipelineStatus(lane);
  revalidatePath("/", "layout");
}

export async function workerHealth(): Promise<{ online: boolean; detail: string }> {
  const running = listRunningPipelines();
  if (running.length) {
    return { online: true, detail: running.map((r) => r.message).join(" · ") };
  }
  try {
    const base = (process.env.PIPELINE_WORKER_URL || "http://127.0.0.1:8787").replace(/\/$/, "");
    const r = await fetch(`${base}/health`, { cache: "no-store", signal: AbortSignal.timeout(1200) });
    if (r.ok) return { online: true, detail: "Ready — jobs & internship pipelines available" };
  } catch {
    /* local spawn still works */
  }
  return { online: true, detail: "Ready — tap Find jobs or Find internships anytime" };
}
