"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2Icon, XIcon } from "lucide-react";
import { clearPipelineStatus, runningPipelines } from "@/app/actions/pipeline";
import type { PipelineStatus } from "@/lib/pipeline-runner";

export function PipelineBanner() {
  const router = useRouter();
  const [items, setItems] = useState<PipelineStatus[]>([]);
  const prevCount = useRef(0);

  useEffect(() => {
    let alive = true;
    let id: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      try {
        const next = await runningPipelines();
        if (!alive) return;
        if (prevCount.current > 0 && next.length === 0) {
          router.refresh();
        }
        prevCount.current = next.length;
        setItems(next);
        id = setTimeout(tick, next.length ? 4000 : 30_000);
      } catch {
        if (alive) id = setTimeout(tick, 30_000);
      }
    };

    void tick();
    return () => {
      alive = false;
      if (id) clearTimeout(id);
    };
  }, [router]);

  if (!items.length) return null;

  return (
    <div className="mx-4 mb-2 flex flex-col gap-2 lg:mx-6">
      {items.map((s) => (
        <div
          key={s.lane}
          className="flex items-center gap-2 rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-sm text-sky-700 dark:text-sky-300"
        >
          <Loader2Icon className="size-4 shrink-0 animate-spin" />
          <span className="rounded border border-sky-500/30 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide opacity-80">
            {s.lane}
          </span>
          <span className="flex-1">{s.message || "Working…"}</span>
          <button
            type="button"
            className="rounded p-0.5 opacity-60 hover:opacity-100"
            aria-label={`Dismiss ${s.lane}`}
            onClick={() => {
              void clearPipelineStatus(s.lane).then(() =>
                setItems((prev) => prev.filter((x) => x.lane !== s.lane)),
              );
            }}
          >
            <XIcon className="size-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
