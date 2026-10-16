import Link from "next/link";
import { ChartAreaInteractive } from "@/components/chart-area-interactive";
import { JobsTable } from "@/components/jobs-table";
import { SectionCards } from "@/components/section-cards";
import { SaveJobButton } from "@/components/save-job-button";
import { StatusBadge } from "@/components/status-badge";
import { dailySeries, listJobs, overview } from "@/lib/db";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { targetLabel } from "@/lib/profile";
import { isSaved } from "@/lib/saved";

export default function Page() {
  requireOnboarding();
  const o = overview();
  const forYou = listJobs({ status: ["matched", "ready", "new"], order: "score", limit: 8 });
  const recent = listJobs({ limit: 6 });
  const label = targetLabel();

  return (
    <div className="flex flex-1 flex-col">
      <div className="@container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
          <div className="mx-4 flex flex-wrap items-end justify-between gap-2 lg:mx-6">
            <div>
              <h2 className="text-lg font-semibold tracking-tight">For you</h2>
              <p className="text-sm text-muted-foreground">
                Jobs agents kept for <span className="text-foreground">{label}</span>
              </p>
            </div>
            <Link href="/jobs" className="text-sm text-muted-foreground hover:text-foreground">
              Browse all jobs
            </Link>
          </div>

          {forYou.length === 0 ? (
            <div className="mx-4 rounded-lg border border-dashed p-4 text-sm text-muted-foreground lg:mx-6">
              No matched roles yet. Run{" "}
              <code className="rounded bg-muted px-1.5 py-0.5">python -m applyforme run</code> after setting Preferences
              — junior seniority automatically hides Senior / Staff / Lead titles.
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
            <JobsTable jobs={recent} empty="No jobs yet." />
          </div>
        </div>
      </div>
    </div>
  );
}
