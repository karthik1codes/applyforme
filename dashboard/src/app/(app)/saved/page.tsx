import Link from "next/link";
import { PageContainer } from "@/components/page-container";
import { SaveJobButton } from "@/components/save-job-button";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { getJob } from "@/lib/db";
import { listSavedIds } from "@/lib/saved";

export default async function SavedPage() {
  await requireOnboarding();
  const jobs = listSavedIds().map((id) => getJob(id)).filter(Boolean);

  return (
    <PageContainer title="Saved Jobs" description="Bookmarks you want to revisit before applying.">
      {jobs.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing saved yet. Bookmark roles from the Jobs page.</p>
      ) : (
        <ul className="divide-y rounded-lg border">
          {jobs.map((j) =>
            j ? (
              <li key={j.id} className="flex items-center justify-between gap-3 p-4">
                <div>
                  <Link href={`/applications/${encodeURIComponent(j.id)}`} className="font-medium hover:underline">
                    {j.title}
                  </Link>
                  <p className="text-sm text-muted-foreground">{j.company}</p>
                </div>
                <SaveJobButton jobId={j.id} saved />
              </li>
            ) : null,
          )}
        </ul>
      )}
    </PageContainer>
  );
}
