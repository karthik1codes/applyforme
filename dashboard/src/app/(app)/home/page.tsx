import Link from "next/link";
import { ChartAreaInteractive } from "@/components/chart-area-interactive";
import { FindJobsButton } from "@/components/find-jobs-button";
import { JobsTable } from "@/components/jobs-table";
import { SectionCards } from "@/components/section-cards";
import { SaveJobButton } from "@/components/save-job-button";
import { StatusBadge } from "@/components/status-badge";
import { dailySeries, listJobs, overview } from "@/lib/db";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { targetLabel } from "@/lib/profile";
import { isSaved } from "@/lib/saved";

export default async function Page({ searchParams }: { searchParams: Promise<{ welcome?: string }> }) {
  await requireOnboarding();
  const { welcome } = await searchParams;
  const o = overview();
  const forYou = listJobs({ status: ["matched", "ready", "new"], order: "score", limit: 8 });
  const recent = listJobs({ limit: 6 });
  const label = targetLabel();

  return (
    <div className="flex flex-1 flex-col">
      <div className="@container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
          {welcome && (
            <div className="mx-4 rounded-2xl border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-900 dark:text-emerald-100 lg:mx-6">
              You&apos;re set. We&apos;re already searching for {label} roles — new matches will appear below.
            </div>
          )}
          <div className="mx-4 flex flex-wrap items-end justify-between gap-3 lg:mx-6">
            <div>
              <h2 className="text-lg font-semibold tracking-tight">For you</h2>
              <p className="text-sm text-muted-foreground">
                Roles matched to <span className="text-foreground">{label}</span>
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <FindJobsButton size="sm" />
              <Link href="/jobs" className="text-sm text-muted-foreground hover:text-foreground">
                Browse all
              </Link>
            </div>
          </div>

          {forYou.length === 0 ? (
            <div className="mx-4 rounded-2xl border border-dashed bg-muted/20 p-8 text-center lg:mx-6">
              <h3 className="text-base font-semibold">No roles yet</h3>
              <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
                Tap below and we&apos;ll search the job boards for openings that fit your level — no terminal needed.
              </p>
              <div className="mt-5 flex justify-center">
                <FindJobsButton label="Find my first jobs" size="lg" />
              </div>
            </div>
          ) : (
            <ul className="mx-4 divide-y rounded-lg border lg:mx-6">
              {forYou.map((j) => (
                <li key={j.id} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <Link href={`/applications/${encodeURIComponent(j.id)}`} className="font-medium hover:underline">
                      {j.title}
                    </Link>
                    <p className="truncate text-sm text-muted-foreground">
                      {j.company} · score {j.score ?? "—"}
                    </p>
                    <a
                      href={j.applyUrl || j.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-sky-600 hover:underline dark:text-sky-400"
                    >
                      Open posting
                    </a>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={j.status} />
                    <SaveJobButton jobId={j.id} saved={isSaved(j.id)} />
                  </div>
                </li>
              ))}
            </ul>
          )}

          <SectionCards o={o} />
          <div className="px-4 lg:px-6">
            <ChartAreaInteractive data={dailySeries(90)} />
          </div>
          <div className="flex flex-col gap-3 px-4 lg:px-6">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">Latest activity</h3>
              <Link href="/applications" className="text-sm text-muted-foreground hover:text-foreground">
                View applications
              </Link>
            </div>
            <JobsTable jobs={recent} empty="Nothing yet — find jobs above to get started." />
          </div>
        </div>
      </div>
    </div>
  );
}
