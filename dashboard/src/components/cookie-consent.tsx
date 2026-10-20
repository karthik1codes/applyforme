"use client";

import { useEffect, useState } from "react";

const KEY = "afm_cookie_consent";

export function CookieConsent() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let open = false;
    try {
      open = !localStorage.getItem(KEY);
    } catch {
      open = true;
    }
    if (!open) return;
    // Defer one tick: reading localStorage is a post-mount concern, not a
    // synchronous cascading render.
    const t = setTimeout(() => setOpen(true), 0);
    return () => clearTimeout(t);
  }, []);

  function accept() {
    try {
      localStorage.setItem(KEY, "accepted");
    } catch {
      /* ignore */
    }
    setOpen(false);
  }

  function decline() {
    try {
      localStorage.setItem(KEY, "declined");
    } catch {
      /* ignore */
    }
    setOpen(false);
  }

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-label="Cookie notice"
      className="fixed bottom-5 left-5 right-5 z-50 mx-auto max-w-md animate-in fade-in slide-in-from-bottom-4 duration-500 sm:left-auto sm:right-6 sm:mx-0"
    >
      <div className="rounded-3xl bg-white p-5 text-black shadow-[rgba(0,0,0,0.1)_0px_20px_25px_-5px,rgba(0,0,0,0.1)_0px_8px_10px_-6px]">
        <p className="font-[family-name:var(--font-landing-body)] text-base font-medium leading-snug">
          We use essential cookies to keep you signed in and optional analytics to improve applyforme.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={accept}
            className="inline-flex min-h-10 min-w-[120px] items-center justify-center rounded border border-transparent bg-black px-4 py-2 text-base font-normal text-white"
          >
            Accept
          </button>
          <button
            type="button"
            onClick={decline}
            className="inline-flex min-h-10 min-w-[120px] items-center justify-center rounded border border-black bg-transparent px-4 py-2 text-base font-normal text-black"
          >
            Decline
          </button>
        </div>
      </div>
    </div>
  );
}
