import Link from "next/link";
import { PageContainer } from "@/components/page-container";
import { SaveJobButton } from "@/components/save-job-button";
import { StatusBadge } from "@/components/status-badge";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { listJobs } from "@/lib/db";
import { targetLabel } from "@/lib/profile";
import { isSaved } from "@/lib/saved";

export default function JobsPage() {
  requireOnboarding();
  const jobs = listJobs({ status: ["new", "matched", "ready", "skipped"], order: "score", limit: 200 });
  // Showcase roles the pipeline kept for the user's target (skip seniority rejects marked skipped with that note)
  const forYou = jobs.filter((j) => j.status !== "skipped" || !j.notes?.includes("seniority"));
  const label = targetLabel();

  return (
    <PageContainer
      title="Jobs"
      description={`Roles fetched for your current target: ${label}. Senior titles are hidden when you set seniority to junior.`}
    >
      {forYou.length === 0 ? (
        <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
          No matching jobs yet. Finish onboarding, then run{" "}
          <code className="rounded bg-muted px-1.5 py-0.5">python -m applyforme run</code> so agents discover and score roles for you.
        </div>
      ) : (
        <ul className="divide-y rounded-lg border">
          {forYou.map((j) => (
            <li key={j.id} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <Link href={`/applications/${encodeURIComponent(j.id)}`} className="font-medium hover:underline">
                  {j.title}
                </Link>
                <p className="truncate text-sm text-muted-foreground">
                  {j.company} · {j.location || "Location n/a"} · score {j.score ?? "—"}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <StatusBadge status={j.status} />
                <SaveJobButton jobId={j.id} saved={isSaved(j.id)} />
                <a href={j.url} target="_blank" rel="noreferrer" className="text-sm text-muted-foreground underline">
                  Posting
                </a>
              </div>
            </li>
          ))}
        </ul>
      )}
    </PageContainer>
  );
}
