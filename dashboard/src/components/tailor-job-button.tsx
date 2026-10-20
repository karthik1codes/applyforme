"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";
import { Loader2Icon, SparklesIcon } from "lucide-react";
import { jobTailorReady, triggerPipeline } from "@/app/actions/pipeline";
import { Button } from "@/components/ui/button";

/** Builds resume PDF + cover letter for one matched job → status becomes Ready. */
export function TailorJobButton({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const startedAt = useRef(0);

  useEffect(() => {
    if (!running) return;
    let alive = true;
    const tick = async () => {
      try {
        const r = await jobTailorReady(jobId);
        if (!alive) return;
        if (r.error) {
          setRunning(false);
          setMsg(`Tailor failed — ${r.error}`);
          router.refresh();
          return;
        }
        if (r.ready) {
          setRunning(false);
          setMsg("Tailor done — Prepare application is unlocked. Resume is below.");
          router.refresh();
          return;
        }
        const elapsed = (Date.now() - startedAt.current) / 1000;
        if (elapsed > 120) {
          setRunning(false);
          setMsg("Still running after 2 minutes — check the pipeline banner / logs, then try again.");
          router.refresh();
          return;
        }
        setMsg(
          r.hasCover
            ? "Almost done — saving resume…"
            : `Tailoring… ${Math.round(elapsed)}s (cover letter + resume PDF)`,
        );
        window.setTimeout(tick, 1500);
      } catch {
        if (alive) window.setTimeout(tick, 4000);
      }
    };
    void tick();
    return () => {
      alive = false;
    };
  }, [running, jobId, router]);

  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        type="button"
        size="sm"
        disabled={pending || running}
        onClick={() =>
          start(async () => {
            setMsg(null);
            startedAt.current = Date.now();
            setRunning(true);
            const r = await triggerPipeline("tailor", 1, jobId);
            if (!r.ok) {
              setRunning(false);
              setMsg(r.message);
            } else {
              setMsg("Started — waiting for resume + cover letter…");
            }
          })
        }
      >
        {pending || running ? <Loader2Icon className="size-4 animate-spin" /> : <SparklesIcon className="size-4" />}
        {pending || running ? "Tailoring…" : "Tailor this job"}
      </Button>
      <p className="max-w-[18rem] text-right text-xs text-muted-foreground">
        {msg || "Creates resume PDF + cover letter. Apply unlocks only after that finishes."}
      </p>
    </div>
  );
}
