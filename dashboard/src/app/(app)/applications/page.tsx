import Link from "next/link";
import { JobsTable } from "@/components/jobs-table";
import { PageContainer } from "@/components/page-container";
import { STATUSES, listJobs, statusCounts, type Status } from "@/lib/db";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { cn } from "@/lib/utils";

const FILTERS: { key: string; label: string; statuses?: Status[] }[] = [
  { key: "all", label: "All" },
  { key: "applied", label: "Applied", statuses: ["applied"] },
  { key: "ready", label: "Ready", statuses: ["ready"] },
  { key: "needs_feedback", label: "Needs feedback", statuses: ["needs_feedback"] },
  { key: "manual", label: "Apply manually", statuses: ["manual"] },
  { key: "matched", label: "Matched", statuses: ["matched"] },
  { key: "failed", label: "Failed", statuses: ["failed"] },
  { key: "skipped", label: "Skipped", statuses: ["skipped"] },
];

export default async function Page({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  requireOnboarding();
  const { status = "all" } = await searchParams;
  const f = FILTERS.find((x) => x.key === status) ?? FILTERS[0];
  const counts = statusCounts();
  const total = STATUSES.reduce((a, s) => a + (counts[s] ?? 0), 0);
  const jobs = listJobs({ status: f.statuses, limit: 200 });

  return (
    <PageContainer title="Recent applications" description="Everything your agents have found, scored and submitted. Newest first.">
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((x) => (
          <Link
            key={x.key}
            href={x.key === "all" ? "/applications" : `/applications?status=${x.key}`}
            className={cn("rounded-full border px-3 py-1 text-sm", x.key === f.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}
          >
            {x.label} <span className="tabular-nums opacity-70">{x.key === "all" ? total : (counts[x.key] ?? 0)}</span>
          </Link>
        ))}
      </div>
      <JobsTable jobs={jobs} empty="Nothing in this view." />
    </PageContainer>
  );
}
