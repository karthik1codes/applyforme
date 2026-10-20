"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Loader2Icon, SendIcon } from "lucide-react";
import { triggerPipeline } from "@/app/actions/pipeline";
import { Button } from "@/components/ui/button";

export function ApplyJobButton({
  jobId,
  label = "Prepare application",
  size = "sm",
}: {
  jobId: string;
  label?: string;
  size?: "default" | "sm" | "lg";
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);

  return (
    <div className="flex flex-col items-start gap-1">
      <Button
        type="button"
        size={size}
        disabled={pending}
        onClick={() =>
          start(async () => {
            setMsg(null);
            const r = await triggerPipeline("apply", 1, jobId);
            setMsg(r.message);
            router.push(`/applications/${encodeURIComponent(jobId)}?applying=1`);
            router.refresh();
          })
        }
      >
        {pending ? <Loader2Icon className="size-4 animate-spin" /> : <SendIcon className="size-4" />}
        {pending ? "Starting…" : label}
      </Button>
      {msg && <p className="max-w-xs text-xs text-muted-foreground">{msg}</p>}
    </div>
  );
}
