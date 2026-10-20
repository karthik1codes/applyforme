"use client";

import Link from "next/link";
import {
  BellIcon,
  BriefcaseIcon,
  CreditCardIcon,
  GraduationCapIcon,
  LogOutIcon,
  RefreshCwIcon,
  ServerIcon,
  Settings2Icon,
  UserIcon,
} from "lucide-react";
import { FindJobsButton } from "@/components/find-jobs-button";
import { logout } from "@/app/actions/auth";

function humanSchedule(cron: string): string {
  const c = (cron || "").trim();
  if (!c || c === "off") return "Paused";
  if (c === "0 */4 * * *") return "Every 4 hours";
  if (c === "15 */6 * * *" || c === "30 */6 * * *") return "Every 6 hours";
  if (c.startsWith("0 */") || c.startsWith("15 */") || c.startsWith("30 */")) {
    const n = c.split(" ")[1]?.replace("*/", "");
    return n ? `Every ${n} hours` : c;
  }
  return c;
}

export function SettingsPanel({
  workerOnline,
  workerDetail,
  scheduleRun,
  scheduleInbox,
  scheduleInternships,
  hostingLabel,
}: {
  workerOnline: boolean;
  workerDetail: string;
  scheduleRun: string;
  scheduleInbox: string;
  scheduleInternships: string;
  hostingLabel: string;
}) {
  return (
    <div className="mx-auto w-full max-w-3xl space-y-10">
      <section className="relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-950 px-6 py-10 text-white md:px-10 md:py-12">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.12]"
          style={{
            backgroundImage:
              "radial-gradient(ellipse 80% 60% at 20% 0%, #ff4c00 0%, transparent 55%), radial-gradient(ellipse 60% 50% at 100% 100%, #00367B 0%, transparent 50%)",
          }}
        />
        <div className="relative">
          <p className="text-sm font-medium text-[#ff4c00]">Your search</p>
          <h2 className="mt-2 text-3xl font-medium tracking-tight md:text-4xl">Jobs find you automatically</h2>
          <p className="mt-3 max-w-xl text-base text-white/75">
            Agents run on your EC2 worker — jobs and internships on separate pipelines. You only approve submits.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <span
              className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm ${
                workerOnline ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-200"
              }`}
            >
              <span className={`size-2 rounded-full ${workerOnline ? "bg-emerald-400" : "bg-amber-400"}`} />
              {workerDetail}
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-sm text-white/80">
              <ServerIcon className="size-3.5" />
              {hostingLabel}
            </span>
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
            <FindJobsButton label="Find new jobs now" size="lg" className="[&_button]:bg-white [&_button]:text-black [&_button]:hover:bg-white/90" />
            <FindJobsButton label="Find internships" stage="internships" size="lg" variant="outline" className="[&_button]:border-white/40 [&_button]:bg-transparent [&_button]:text-white" />
            <FindJobsButton label="Check employer inbox" stage="inbox" size="lg" variant="outline" className="[&_button]:border-white/40 [&_button]:bg-transparent [&_button]:text-white" />
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-2xl border bg-card/40 p-5">
          <div className="flex items-center gap-2 text-sm font-medium">
            <BriefcaseIcon className="size-4 text-muted-foreground" />
            Jobs pipeline
          </div>
          <p className="mt-2 text-2xl font-semibold tracking-tight">{humanSchedule(scheduleRun)}</p>
          <p className="mt-1 text-sm text-muted-foreground">EC2 cron · full-time roles</p>
        </div>
        <div className="rounded-2xl border bg-card/40 p-5">
          <div className="flex items-center gap-2 text-sm font-medium">
            <GraduationCapIcon className="size-4 text-muted-foreground" />
            Internships pipeline
          </div>
          <p className="mt-2 text-2xl font-semibold tracking-tight">{humanSchedule(scheduleInternships)}</p>
          <p className="mt-1 text-sm text-muted-foreground">Separate lane · Glassdoor / Wellfound</p>
        </div>
        <div className="rounded-2xl border bg-card/40 p-5">
          <div className="flex items-center gap-2 text-sm font-medium">
            <BellIcon className="size-4 text-muted-foreground" />
            Email inbox
          </div>
          <p className="mt-2 text-2xl font-semibold tracking-tight">{humanSchedule(scheduleInbox)}</p>
          <p className="mt-1 text-sm text-muted-foreground">Recruiter replies via IMAP</p>
        </div>
      </section>

      <section>
        <h3 className="mb-3 text-sm font-medium tracking-wide text-muted-foreground uppercase">Your account</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {[
            { href: "/preferences", icon: Settings2Icon, title: "Preferences", blurb: "Seniority, titles, locations" },
            { href: "/profile", icon: UserIcon, title: "Profile", blurb: "Name, socials, skills" },
            { href: "/onboarding?force=1", icon: RefreshCwIcon, title: "Onboarding", blurb: "Redo setup wizard" },
            { href: "/billing", icon: CreditCardIcon, title: "Billing", blurb: "Plans and payment" },
          ].map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-start gap-3 rounded-2xl border p-4 transition hover:bg-muted/40"
            >
              <item.icon className="mt-0.5 size-5 text-muted-foreground" />
              <span>
                <span className="block font-medium">{item.title}</span>
                <span className="text-sm text-muted-foreground">{item.blurb}</span>
              </span>
            </Link>
          ))}
          <form action={logout} className="sm:col-span-2">
            <button
              type="submit"
              className="flex w-full items-start gap-3 rounded-2xl border border-destructive/30 p-4 text-left transition hover:bg-destructive/5"
            >
              <LogOutIcon className="mt-0.5 size-5 text-muted-foreground" />
              <span>
                <span className="block font-medium">Sign out</span>
                <span className="text-sm text-muted-foreground">
                  Return to the landing page — use Start applying to sign in and continue onboarding
                </span>
              </span>
            </button>
          </form>
        </div>
      </section>
    </div>
  );
}
