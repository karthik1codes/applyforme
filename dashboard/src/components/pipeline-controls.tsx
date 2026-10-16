"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

const STAGES = ["run", "discover", "match", "tailor", "inbox"] as const;

export function PipelineControls({ secretConfigured }: { secretConfigured: boolean }) {
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function trigger(stage: string) {
    setBusy(true);
    setMsg(null);
    try {
      const secret = sessionStorage.getItem("afm_pipeline_secret") || "";
      if (!secret) {
        setMsg("Paste your PIPELINE_WEBHOOK_SECRET below once (stored only in this browser).");
        setBusy(false);
        return;
      }
      const res = await fetch("/api/pipeline/webhook", {
        method: "POST",
        headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/json" },
        body: JSON.stringify({ stage, async: true }),
      });
      const data = await res.json();
      setMsg(res.ok ? `Accepted: ${stage} (check worker logs / Jobs page in a few minutes)` : `Error ${res.status}: ${data.error || JSON.stringify(data)}`);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4 rounded-lg border p-4">
      <div>
        <h3 className="font-medium">Trigger pipeline</h3>
        <p className="text-sm text-muted-foreground">
          Fires the EC2 worker over the same webhook EventBridge uses. {secretConfigured ? "Server secret is configured." : "Set PIPELINE_WEBHOOK_SECRET on the server first."}
        </p>
      </div>
      <label className="block space-y-1 text-sm">
        <span className="text-muted-foreground">Webhook secret (browser-only)</span>
        <input
          type="password"
          className="w-full max-w-md rounded-md border bg-background px-3 py-2"
          placeholder="PIPELINE_WEBHOOK_SECRET"
          onChange={(e) => sessionStorage.setItem("afm_pipeline_secret", e.target.value.trim())}
        />
      </label>
      <div className="flex flex-wrap gap-2">
        {STAGES.map((s) => (
          <Button key={s} type="button" size="sm" variant="outline" disabled={busy || !secretConfigured} onClick={() => trigger(s)}>
            {s}
          </Button>
        ))}
      </div>
      {msg && <p className="text-sm text-muted-foreground">{msg}</p>}
    </div>
  );
}
