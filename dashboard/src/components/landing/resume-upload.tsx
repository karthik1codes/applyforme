"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Variant = "landing" | "profile";

export function ResumeUpload({
  redirectTo = "/home",
  variant = "landing",
  label,
}: {
  /** Pass empty string to stay on the page and refresh. */
  redirectTo?: string;
  variant?: Variant;
  label?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function onChange(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const body = new FormData();
      body.set("resume", file);
      const res = await fetch("/api/resume", { method: "POST", body });
      const data = (await res.json()) as {
        ok?: boolean;
        error?: string;
        imported?: boolean;
        roles?: number;
        skills?: number;
        education?: number;
        projects?: number;
        honors?: number;
        importMessage?: string;
      };
      if (!res.ok) throw new Error(data.error || "Upload failed");
      setDone(true);
      if (data.imported) {
        setNote(
          `Filled profile from resume: ${data.roles ?? 0} roles, ${data.skills ?? 0} skills, ${data.education ?? 0} education, ${data.projects ?? 0} projects, ${data.honors ?? 0} honors. Tailor uses this for job PDFs.`,
        );
      } else if (data.importMessage) {
        setNote(`Saved file. Could not auto-parse yet: ${data.importMessage}`);
      }
      if (redirectTo) {
        router.push(redirectTo);
      }
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  const buttonClass =
    variant === "profile"
      ? "inline-flex min-h-10 w-full items-center justify-center rounded-md bg-foreground px-4 py-2 text-sm text-background transition hover:opacity-90 disabled:opacity-60"
      : "inline-flex min-h-10 min-w-[160px] items-center justify-center rounded border border-white bg-transparent px-4 py-2 text-base font-normal text-white transition hover:bg-white/10 disabled:opacity-60";

  const idleLabel = label || (variant === "profile" ? "Upload or replace resume" : "Upload resume");

  return (
    <div className={variant === "profile" ? "flex w-full flex-col gap-3" : "flex flex-col items-start gap-3"}>
      <input
        ref={input}
        type="file"
        accept=".pdf,.txt,.doc,.docx,application/pdf,text/plain"
        className="sr-only"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
      <button type="button" disabled={busy} onClick={() => input.current?.click()} className={buttonClass}>
        {busy ? "Uploading & parsing…" : done ? "Uploaded" : idleLabel}
      </button>
      {error && (
        <p className={variant === "profile" ? "text-sm text-red-500" : "text-sm text-[#ff4c00]"}>{error}</p>
      )}
      {note && !error && <p className="text-sm text-muted-foreground">{note}</p>}
    </div>
  );
}
