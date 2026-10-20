import Link from "next/link";
import { FindJobsButton } from "@/components/find-jobs-button";
import { JobLinks } from "@/components/job-links";
import { PageContainer } from "@/components/page-container";
import { SaveJobButton } from "@/components/save-job-button";
import { StatusBadge } from "@/components/status-badge";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { listInternships } from "@/lib/db";
import { isSaved } from "@/lib/saved";

const SOURCES = ["Glassdoor", "Wellfound", "LinkedIn", "Indeed", "Remotive", "Google", "Naukri", "ZipRecruiter"];

export default async function InternshipsPage() {
  await requireOnboarding();
  const roles = listInternships(200);

  return (
    <PageContainer
      title="Internships"
      description="Internship, trainee, and co-op roles pulled from Glassdoor, Wellfound, LinkedIn, and other boards — separate from full-time Jobs."
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">{roles.length} internship openings</p>
          <p className="mt-1 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
            {SOURCES.map((s) => (
              <span key={s} className="rounded-md border px-1.5 py-0.5">
                {s}
              </span>
            ))}
          </p>
        </div>
        <FindJobsButton label="Find internships" stage="internships" size="sm" />
      </div>

      {roles.length === 0 ? (
        <div className="rounded-2xl border border-dashed p-8 text-center">
          <h3 className="text-base font-semibold">No internships yet</h3>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            We&apos;ll search Glassdoor, Wellfound (AngelList), LinkedIn, Indeed, Remotive, and Google Jobs for roles that match your target titles.
          </p>
          <div className="mt-5 flex justify-center">
            <FindJobsButton label="Find internships for me" stage="internships" size="lg" />
          </div>
        </div>
      ) : (
        <ul className="divide-y rounded-lg border">
          {roles.map((j) => (
            <li key={j.id} className="flex flex-col gap-3 p-4">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <Link href={`/applications/${encodeURIComponent(j.id)}`} className="font-medium hover:underline">
                    {j.title}
                  </Link>
                  <p className="truncate text-sm text-muted-foreground">
                    {j.company} · {j.location || "Location n/a"}
                    {j.score != null ? ` · score ${j.score}` : ""}
                    {j.ats ? ` · ${j.ats}` : ""}
                  </p>
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
