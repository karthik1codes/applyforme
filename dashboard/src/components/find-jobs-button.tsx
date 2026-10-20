"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { Loader2Icon, SparklesIcon } from "lucide-react";
import { pipelineStatus, triggerPipeline } from "@/app/actions/pipeline";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { laneForStage, type PipelineLane } from "@/lib/pipeline-lanes";

function friendly(msg: string): string {
  if (/UnicodeEncodeError|charmap|Traceback|\[\d|Failed \(\d\)/.test(msg)) {
    return "Couldn’t finish that search. Try again in a moment.";
  }
  return msg;
}

export function FindJobsButton({
  label = "Find jobs for me",
  stage = "run",
  className,
  size = "default",
  variant = "default",
}: {
  label?: string;
  stage?: string;
  className?: string;
  size?: "default" | "sm" | "lg";
  variant?: "default" | "outline" | "secondary";
}) {
  const router = useRouter();
  const lane: PipelineLane = laneForStage(stage);
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    let alive = true;
    let id: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      try {
        // Only watch THIS button's lane — jobs running won't disable internships
        const s = await pipelineStatus(lane);
        if (!alive) return;
        setRunning(s.state === "running");
        id = setTimeout(tick, s.state === "running" ? 4000 : 45_000);
      } catch {
        if (alive) id = setTimeout(tick, 45_000);
      }
    };
    void tick();
    return () => {
      alive = false;
      if (id) clearTimeout(id);
    };
  }, [lane]);

  return (
    <div className={cn("flex flex-col items-start gap-2", className)}>
      <Button
        type="button"
        size={size}
        variant={variant}
        disabled={pending || running}
        onClick={() =>
          start(async () => {
            setMsg(null);
            setRunning(true);
            const r = await triggerPipeline(stage);
            setMsg(friendly(r.message));
            setRunning(r.ok);
            router.refresh();
            window.setTimeout(() => setMsg(null), 8000);
          })
        }
      >
        {pending || running ? <Loader2Icon className="size-4 animate-spin" /> : <SparklesIcon className="size-4" />}
        {pending || running ? "Searching…" : label}
      </Button>
      {msg && <p className="max-w-md text-xs text-muted-foreground">{msg}</p>}
    </div>
  );
}
