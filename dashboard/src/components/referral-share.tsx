"use client";

import { useEffect, useState } from "react";

export function ReferralShare({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  const [origin, setOrigin] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setOrigin(window.location.origin), 0);
    return () => clearTimeout(t);
  }, []);

  async function copy() {
    const link = `${origin || window.location.origin}/?ref=${encodeURIComponent(code)}`;
    const text = `Join me on applyforme — use code ${code}: ${link}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="mt-4 flex flex-wrap gap-2">
      <button
        type="button"
        onClick={copy}
        className="rounded-md bg-foreground px-3 py-2 text-sm text-background"
      >
        {copied ? "Copied" : "Copy invite"}
      </button>
      <p className="w-full text-xs text-muted-foreground">
        Friends open the landing page with <span className="font-mono">?ref={code}</span> or paste the code in onboarding.
      </p>
    </div>
  );
}
