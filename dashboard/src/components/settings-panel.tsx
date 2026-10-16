"use client";

import Link from "next/link";
import { useState, useTransition } from "react";
import {
  BellIcon,
  BriefcaseIcon,
  CreditCardIcon,
  RefreshCwIcon,
  Settings2Icon,
  UserIcon,
  ZapIcon,
} from "lucide-react";
import { triggerPipeline, type TriggerResult } from "@/app/actions/pipeline";
import { Button } from "@/components/ui/button";

function humanSchedule(cron: string): string {
  const c = (cron || "").trim();
  if (!c || c === "off") return "Paused";
  if (c === "0 */4 * * *") return "Every 4 hours";
  if (c === "30 */6 * * *") return "Every 6 hours";
  if (c.startsWith("0 */")) {
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
  automationReady,
}: {
  workerOnline: boolean;
  workerDetail: string;
  scheduleRun: string;
  scheduleInbox: string;
  automationReady: boolean;
}) {
  const [pending, start] = useTransition();
  const [result, setResult] = useState<TriggerResult | null>(null);
  const [advanced, setAdvanced] = useState(false);

  function go(stage: string) {
    start(async () => setResult(await triggerPipeline(stage)));
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-10">
      {/* Hero — user-first, same calm hierarchy as the landing */}
      <section className="relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-zinc-950 via-zinc-900 to-zinc-950 px-6 py-10 text-white md:px-10 md:py-12">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.12]"
          style={{
            backgroundImage:
              "radial-gradient(ellipse 80% 60% at 20% 0%, #ff4c00 0%, transparent 55%), radial-gradient(ellipse 60% 50% at 100% 100%, #00367B 0%, transparent 50%)",
          }}
        />
        <div className="relative">
          <p className="font-[family-name:var(--font-landing-body)] text-sm font-medium text-[#ff4c00]">Your search</p>
          <h2 className="mt-2 font-[family-name:var(--font-landing-display)] text-3xl font-medium tracking-tight md:text-4xl">
            Jobs find you on a schedule
          </h2>
          <p className="mt-3 max-w-xl font-[family-name:var(--font-landing-body)] text-base text-white/75">
            applyforme looks for roles that match your seniority and titles in the background. You approve every application — nothing submits itself.
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
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            <Button
              type="button"
              size="lg"
              disabled={pending || !automationReady}
              onClick={() => go("run")}
              className="min-w-[180px] bg-white text-black hover:bg-white/90"
            >
              <ZapIcon className="size-4" />
              {pending ? "Starting…" : "Find new jobs now"}
            </Button>
            <Button
              type="button"
              size="lg"
              variant="outline"
              disabled={pending || !automationReady}
              onClick={() => go("inbox")}
              className="border-white/40 bg-transparent text-white hover:bg-white/10"
            >
              <BellIcon className="size-4" />
              Check employer inbox
            </Button>
          </div>
          {result && (
            <p className={`mt-4 text-sm ${result.ok ? "text-emerald-300" : "text-amber-200"}`}>{result.message}</p>
          )}
          {!automationReady && (
            <p className="mt-4 text-sm text-white/60">
              Automation isn’t wired on this machine yet. After you deploy to EC2, this button works with one click.
            </p>
          )}
        </div>
      </section>

      {/* Plain-language schedule */}
      <section className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-2xl border bg-card/40 p-5">
          <div className="flex items-center gap-2 text-sm font-medium">
            <BriefcaseIcon className="size-4 text-muted-foreground" />
            Job search
          </div>
          <p className="mt-2 text-2xl font-semibold tracking-tight">{humanSchedule(scheduleRun)}</p>
          <p className="mt-1 text-sm text-muted-foreground">Discover, score, and tailor resumes for your target level.</p>
        </div>
        <div className="rounded-2xl border bg-card/40 p-5">
          <div className="flex items-center gap-2 text-sm font-medium">
            <BellIcon className="size-4 text-muted-foreground" />
            Email inbox
          </div>
          <p className="mt-2 text-2xl font-semibold tracking-tight">{humanSchedule(scheduleInbox)}</p>
          <p className="mt-1 text-sm text-muted-foreground">Matches recruiter replies to jobs you’ve already applied to.</p>
        </div>
      </section>

      {/* Account shortcuts */}
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
        </div>
      </section>

      {/* Advanced — collapsed ops */}
      <section className="border-t pt-6">
        <button
          type="button"
          onClick={() => setAdvanced((v) => !v)}
          className="text-sm font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          {advanced ? "Hide" : "Show"} advanced (deploy & webhooks)
        </button>
        {advanced && (
          <div className="mt-4 space-y-4 rounded-2xl border bg-muted/20 p-5 text-sm text-muted-foreground">
            <p>
              Worker command: <code className="rounded bg-muted px-1.5 text-foreground">python -m applyforme serve</code>
              . Public webhook: <code className="rounded bg-muted px-1.5 text-foreground">POST /api/pipeline/webhook</code>
            </p>
            <p>
              Cron env: <code className="rounded bg-muted px-1">SCHEDULE_RUN={scheduleRun}</code>
              {" · "}
              <code className="rounded bg-muted px-1">SCHEDULE_INBOX={scheduleInbox}</code>
            </p>
            <div className="flex flex-wrap gap-2">
              {(["discover", "match", "tailor"] as const).map((s) => (
                <Button key={s} type="button" size="sm" variant="outline" disabled={pending || !automationReady} onClick={() => go(s)}>
                  {s}
                </Button>
              ))}
            </div>
            <pre className="overflow-x-auto rounded-lg bg-zinc-950 p-4 text-xs text-zinc-300">
{`# Push latest code to EC2 and go live
git push origin main
ssh ubuntu@YOUR_EC2_IP
cd /opt/applyforme
git pull
sudo bash deploy/ec2/setup.sh
sudo systemctl restart applyforme-worker applyforme-web`}
            </pre>
          </div>
        )}
      </section>
    </div>
  );
}
