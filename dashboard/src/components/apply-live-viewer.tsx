"use client";

import { useEffect, useState } from "react";
import { MonitorPlayIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type LiveMeta = {
  active?: boolean;
  phase?: string;
  note?: string;
  url?: string;
  company?: string;
  title?: string;
  job_id?: string;
  has_image?: boolean;
  headed?: boolean;
  age_sec?: number;
  engine?: string;
  live_view_url?: string;
};

/** Polls the agent's Chromium screenshots so you can watch Apply like a user. */
export function ApplyLiveViewer({ jobId, force }: { jobId?: string; force?: boolean }) {
  const [meta, setMeta] = useState<LiveMeta | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const r = await fetch("/api/apply-live?format=meta", { cache: "no-store" });
        if (!r.ok) return;
        const j = (await r.json()) as LiveMeta;
        if (!alive) return;
        if (jobId && j.job_id && j.job_id !== jobId && !force) {
          setMeta(null);
          return;
        }
        setMeta(j);
        if (j.active || force) setTick((t) => t + 1);
      } catch {
        /* ignore */
      }
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [jobId, force]);

  if (!meta?.active && !force) return null;
  if (!meta) return null;

  const show =
    meta.active || (force && (meta.has_image || !!meta.live_view_url));

  if (!show && !force) return null;

  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <MonitorPlayIcon className="size-4 text-sky-600" />
          Live browser
          {meta.phase && (
            <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-normal text-muted-foreground uppercase">
              {meta.phase}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {meta.engine === "firecrawl"
            ? "Firecrawl cloud browser — interact in the stream below (or open the live URL)"
            : meta.headed === false
              ? "Headless mode — set APPLYFORME_BROWSER_HEADED=1 for a real window"
              : "A Chromium window is open on this machine — you can click/type there too"}
        </p>
      </div>
      <div className="space-y-2 p-3">
        {(meta.company || meta.title) && (
          <p className="text-sm">
            <span className="font-medium">{meta.company}</span>
            {meta.title ? ` — ${meta.title}` : ""}
          </p>
        )}
        {meta.note && <p className="text-xs text-muted-foreground">{meta.note}</p>}
        {meta.url && (
          <a href={meta.url} target="_blank" rel="noreferrer" className="block truncate text-xs text-sky-600 hover:underline">
            {meta.url}
          </a>
        )}
        {meta.live_view_url && (
          <a
            href={meta.live_view_url}
            target="_blank"
            rel="noreferrer"
            className="block truncate text-xs text-sky-600 hover:underline"
          >
            Open Firecrawl live view
          </a>
        )}
        <div className={cn("relative aspect-[16/10] overflow-hidden rounded-lg border bg-zinc-100 dark:bg-zinc-900")}>
          {meta.live_view_url ? (
            <iframe
              key={meta.live_view_url}
              src={meta.live_view_url}
              title="Firecrawl live browser"
              className="h-full w-full border-0"
              allow="clipboard-read; clipboard-write"
            />
          ) : meta.has_image ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={tick}
              src={`/api/apply-live?format=png&t=${tick}`}
              alt="Live application browser"
              className="h-full w-full object-contain object-top"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Waiting for the agent browser…
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
