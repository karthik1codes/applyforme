import Link from "next/link";
import { PageContainer } from "@/components/page-container";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { listJobs } from "@/lib/db";
import { targetLabel } from "@/lib/profile";

export default function AtsPage() {
  requireOnboarding();
  const scored = listJobs({ status: ["matched", "ready", "applied", "skipped", "failed"], order: "score", limit: 100 })
    .filter((j) => j.score != null);

  return (
    <PageContainer
      title="ATS Score"
      description={`Match scores (0–100) against your profile for ${targetLabel()}. Keywords the scorer extracted feed resume tailoring.`}
    >
      {scored.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No scores yet. Run <code className="rounded bg-muted px-1">python -m applyforme match</code> after discover.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left">
              <tr>
                <th className="p-3 font-medium">Score</th>
                <th className="p-3 font-medium">Role</th>
                <th className="p-3 font-medium">Why</th>
              </tr>
            </thead>
            <tbody>
              {scored.map((j) => (
                <tr key={j.id} className="border-t">
                  <td className="p-3 font-semibold tabular-nums">{j.score}</td>
                  <td className="p-3">
                    <Link href={`/applications/${encodeURIComponent(j.id)}`} className="hover:underline">
                      {j.title}
                    </Link>
                    <div className="text-muted-foreground">{j.company}</div>
                  </td>
                  <td className="max-w-md p-3 text-muted-foreground">
                    {(j.reasons || []).slice(0, 2).join(" · ") || (j.redFlags[0] ?? "—")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageContainer>
  );
}
