"use client";

import { useState } from "react";
import { DownloadIcon, MinusIcon, PlusIcon, RotateCcwIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

const ZOOM_MIN = 75;
const ZOOM_MAX = 200;
const ZOOM_STEP = 25;

/** PDF iframe with zoom + download for tailored resumes. */
export function ResumePdfViewer({ src, title, filename }: { src: string; title: string; filename: string }) {
  const [zoom, setZoom] = useState(100);
  // pdf.js-style zoom via CSS transform on wrapper; iframe itself stays readable
  return (
    <div className="mt-2 overflow-hidden rounded-md border bg-white">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/40 px-2 py-1.5">
        <div className="flex items-center gap-1">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={zoom <= ZOOM_MIN}
            aria-label="Zoom out"
            onClick={() => setZoom((z) => Math.max(ZOOM_MIN, z - ZOOM_STEP))}
          >
            <MinusIcon className="size-3.5" />
          </Button>
          <span className="min-w-12 text-center text-xs tabular-nums text-muted-foreground">{zoom}%</span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={zoom >= ZOOM_MAX}
            aria-label="Zoom in"
            onClick={() => setZoom((z) => Math.min(ZOOM_MAX, z + ZOOM_STEP))}
          >
            <PlusIcon className="size-3.5" />
          </Button>
          <Button type="button" size="sm" variant="ghost" aria-label="Reset zoom" onClick={() => setZoom(100)}>
            <RotateCcwIcon className="size-3.5" />
          </Button>
        </div>
        <a
          href={src.includes("?") ? `${src}&download` : `${src}?download`}
          download={filename}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border bg-background px-2.5 text-xs font-medium hover:bg-muted"
        >
          <DownloadIcon className="size-3.5" /> Download PDF
        </a>
      </div>
      <div className="h-[28rem] overflow-auto bg-zinc-200/50">
        <div
          className="origin-top-left transition-transform duration-150"
          style={{
            transform: `scale(${zoom / 100})`,
            width: `${10000 / zoom}%`,
            height: `${(28 * 100) / zoom}rem`,
          }}
        >
          <iframe title={title} loading="lazy" src={`${src}#toolbar=0&navpanes=0`} className="h-full w-full border-0 bg-white" />
        </div>
      </div>
    </div>
  );
}
