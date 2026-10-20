import Link from "next/link";
import { FindJobsButton } from "@/components/find-jobs-button";
import { JobLinks } from "@/components/job-links";
import { PageContainer } from "@/components/page-container";
import { SaveJobButton } from "@/components/save-job-button";
import { StatusBadge } from "@/components/status-badge";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { listJobs } from "@/lib/db";
import { targetLabel } from "@/lib/profile";
import { isSaved } from "@/lib/saved";

export default async function JobsPage() {
  await requireOnboarding();
  const jobs = listJobs({ status: ["new", "matched", "ready", "skipped"], order: "score", limit: 200 });
  // Full-time board — internships live under /internships
  const forYou = jobs.filter(
    (j) =>
      j.category !== "Internship" &&
      !/\bintern(ship)?\b/i.test(j.title) &&
      (j.status !== "skipped" || !j.notes?.includes("seniority")),
  );
  const label = targetLabel();

  return (
    <PageContainer
      title="Jobs"
      description={`Openings for ${label}. Posting and careers links come from Crustdata + the boards.`}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{forYou.length} roles on your board</p>
        <FindJobsButton label="Refresh jobs" size="sm" />
      </div>
      {forYou.length === 0 ? (
        <div className="rounded-2xl border border-dashed p-8 text-center">
          <p className="text-sm text-muted-foreground">No matching jobs yet. Start a search — we&apos;ll handle the rest.</p>
          <div className="mt-4 flex justify-center">
            <FindJobsButton label="Find jobs for me" size="lg" />
          </div>
        </div>
      ) : (
        <ul className="divide-y rounded-lg border">
          {forYou.map((j) => (
            <li key={j.id} className="flex flex-col gap-3 p-4">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <Link href={`/applications/${encodeURIComponent(j.id)}`} className="font-medium hover:underline">
                    {j.title}
                  </Link>
                  <p className="truncate text-sm text-muted-foreground">
                    {j.company} · {j.location || "Location n/a"} · score {j.score ?? "—"}
                  </p>
                  <p className="mt-1 break-all text-xs text-muted-foreground">{j.applyUrl || j.url}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <StatusBadge status={j.status} />
                  <SaveJobButton jobId={j.id} saved={isSaved(j.id)} />
                </div>
              </div>
              <JobLinks
                url={j.url}
                applyUrl={j.applyUrl}
                careersUrl={j.careersUrl}
                companyWebsite={j.companyWebsite}
                companyLinkedin={j.companyLinkedin}
              />
            </li>
          ))}
        </ul>
      )}
    </PageContainer>
  );
}
