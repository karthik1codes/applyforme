import Link from "next/link";
import { PageContainer } from "@/components/page-container";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { listJobs } from "@/lib/db";

export default function CoverLettersPage() {
  requireOnboarding();
  const withCover = listJobs({ status: ["ready", "applied", "needs_feedback", "manual"], limit: 100 }).filter((j) => j.coverLetter);

  return (
    <PageContainer title="Cover Letters" description="Per-job letters the tailor agent wrote. Facts are validated against your profile.">
      {withCover.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          None yet. Run <code className="rounded bg-muted px-1">python -m applyforme tailor</code> on matched jobs.
        </p>
      ) : (
        <ul className="space-y-4">
          {withCover.map((j) => (
            <li key={j.id} className="rounded-lg border p-4">
              <div className="mb-2 flex items-baseline justify-between gap-2">
                <Link href={`/applications/${encodeURIComponent(j.id)}`} className="font-medium hover:underline">
                  {j.title} · {j.company}
                </Link>
                <span className="text-xs text-muted-foreground">{j.status}</span>
              </div>
              <p className="whitespace-pre-wrap text-sm text-muted-foreground line-clamp-6">{j.coverLetter}</p>
            </li>
          ))}
        </ul>
      )}
    </PageContainer>
  );
}
