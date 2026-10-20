"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangleIcon, BanIcon, CheckCircle2Icon, Loader2Icon, PlayIcon, SendIcon } from "lucide-react";
import {
  applySessionState,
  cancelApplication,
  prepareApplication,
  submitApplication,
  type TriggerResult,
} from "@/app/actions/pipeline";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function ApplyReviewCard({
  jobId,
  status,
  hasCoverLetter,
  initialState,
  confirmation,
  submitAttempted,
  lastError,
}: {
  jobId: string;
  status: string;
  hasCoverLetter: boolean;
  initialState: string | null;
  confirmation: string | null;
  submitAttempted: boolean;
  lastError: string;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [currentStatus, setCurrentStatus] = useState(status);
  const [state, setState] = useState(initialState);
  const [msg, setMsg] = useState<string | null>(lastError || null);
  const [submitted, setSubmitted] = useState(status === "applied");
  const [attempted, setAttempted] = useState(submitAttempted);

  // While the applier owns the browser, refresh when it reaches review or finishes.
  useEffect(() => {
    if (!["in_progress", "awaiting_review"].includes(currentStatus)) return;
    let alive = true;
    const poll = async () => {
      try {
        const s = await applySessionState(jobId);
        if (!alive) return;
        const currentAwaiting = currentStatus === "awaiting_review" || state === "AWAITING_USER_REVIEW";
        if (
          s.submitted ||
          s.status !== currentStatus ||
          s.state !== state ||
          s.awaitingReview !== currentAwaiting
        ) {
          setCurrentStatus(s.status);
          setState(s.state);
          setSubmitted(s.submitted);
          setAttempted(s.submitAttempted);
          if (s.lastError && !s.awaitingReview) setMsg(s.lastError);
          router.refresh();
        }
      } catch {
        /* transient */
      }
    };
    const id = setInterval(poll, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [currentStatus, state, jobId, router]);

  const run = (action: () => Promise<TriggerResult>, confirmText?: string) =>
    start(async () => {
      if (confirmText && !window.confirm(confirmText)) return;
      setMsg(null);
      const r = await action();
      setMsg(r.message);
      router.refresh();
    });

  const busy = pending || currentStatus === "in_progress";
  const awaiting = currentStatus === "awaiting_review" || state === "AWAITING_USER_REVIEW";

  if (submitted || currentStatus === "applied") {
    return (
      <Card className="border-emerald-500/30 bg-emerald-500/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CheckCircle2Icon className="size-4 text-emerald-600" /> Application submitted
          </CardTitle>
          <CardDescription>
            {confirmation || "A confirmation was recorded for this application."} No second submission will be sent.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card className={awaiting ? "border-sky-500/40 bg-sky-500/5" : undefined}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {awaiting ? <SendIcon className="size-4 text-sky-600" /> : <PlayIcon className="size-4 text-sky-600" />}
          {awaiting ? "Ready for your review" : currentStatus === "cancelled" ? "Application cancelled" : "Apply with agent"}
        </CardTitle>
        <CardDescription>
          {awaiting
            ? "The form is filled and validated. Check it in the live browser, edit anything you need, then submit this one application. Nothing is sent until you press Submit application."
            : currentStatus === "cancelled"
              ? "The applier stopped before submission. You can prepare the form again."
              : hasCoverLetter
                ? "The agent opens the real application, fills only verified profile facts, validates the form, and stops for your review. Submission is a separate, explicit action."
                : "Tailor the resume and cover letter first."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {attempted && (
          <p className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-sm text-amber-800 dark:text-amber-200">
            <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" />
            A previous submit click was recorded but no confirmation was seen. Check the site and your email before
            retrying; the agent will not submit twice automatically.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {awaiting ? (
            <>
              <Button
                type="button"
                disabled={pending || attempted}
                onClick={() =>
                  run(
                    () => submitApplication(jobId),
                    "Submit this one application now? This sends it to the employer and cannot be undone.",
                  )
                }
              >
                {pending ? <Loader2Icon className="size-4 animate-spin" /> : <SendIcon className="size-4" />}
                {pending ? "Submitting…" : "Submit application"}
              </Button>
              <Button type="button" variant="outline" disabled={pending} onClick={() => run(() => cancelApplication(jobId))}>
                <BanIcon className="size-4" /> Cancel
              </Button>
            </>
          ) : busy ? (
            <>
              <Button type="button" disabled>
                <Loader2Icon className="size-4 animate-spin" /> Preparing…
              </Button>
              <Button type="button" variant="outline" disabled={pending} onClick={() => run(() => cancelApplication(jobId))}>
                <BanIcon className="size-4" /> Cancel
              </Button>
            </>
          ) : (
            <Button
              type="button"
              disabled={pending || !hasCoverLetter || attempted}
              onClick={() => run(() => prepareApplication(jobId))}
            >
              {pending ? <Loader2Icon className="size-4 animate-spin" /> : <PlayIcon className="size-4" />}
              {pending ? "Starting…" : currentStatus === "cancelled" ? "Prepare again" : "Prepare application"}
            </Button>
          )}
        </div>
        {msg && (
          <p className="rounded-md border bg-muted/40 p-2 text-sm text-muted-foreground" role="status">
            {msg}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
