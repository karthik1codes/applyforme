"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

export function ResumeUpload({ redirectTo = "/home" }: { redirectTo?: string }) {
  const input = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function onChange(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.set("resume", file);
      const res = await fetch("/api/resume", { method: "POST", body });
      const data = (await res.json()) as { ok?: boolean; error?: string };
      if (!res.ok) throw new Error(data.error || "Upload failed");
      setDone(true);
      router.push(redirectTo);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-3">
      <input
        ref={input}
        type="file"
        accept=".pdf,.txt,.doc,.docx,application/pdf,text/plain"
        className="sr-only"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
      <button
        type="button"
        disabled={busy}
        onClick={() => input.current?.click()}
        className="inline-flex min-h-10 min-w-[160px] items-center justify-center rounded border border-white bg-transparent px-4 py-2 text-base font-normal text-white transition hover:bg-white/10 disabled:opacity-60"
      >
        {busy ? "Uploading…" : done ? "Uploaded" : "Upload resume"}
      </button>
      {error && <p className="text-sm text-[#ff4c00]">{error}</p>}
    </div>
  );
}
