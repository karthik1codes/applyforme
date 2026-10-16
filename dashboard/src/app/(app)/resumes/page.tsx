import Link from "next/link";
import { PageContainer } from "@/components/page-container";
import { OverleafButton, ResumeLinks } from "@/components/resume-actions";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { resumesByCategory, type Job } from "@/lib/db";
import { readOutput } from "@/lib/files";

function ResumeCard({ job }: { job: Job }) {
  const tex = readOutput(job.resumeTex);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          <Link href={`/applications/${encodeURIComponent(job.id)}`} className="hover:underline">
            {job.title}
          </Link>
        </CardTitle>
        <CardDescription className="flex flex-wrap items-center gap-2">
          {job.company}
          <StatusBadge status={job.status} />
          {job.score !== null && <Badge variant="outline">Match {job.score}</Badge>}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <ResumeLinks pdf={job.resumePdf} tex={job.resumeTex} />
          {tex && <OverleafButton tex={tex} name={`${job.company}-${job.title}`.replace(/[^\w-]+/g, "-").slice(0, 60)} />}
        </div>
        {job.resumePdf && (
          <details>
            <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">Preview</summary>
            <iframe
              title={`${job.company} resume`}
              loading="lazy"
              src={`/api/files/${encodeURIComponent(job.resumePdf)}#toolbar=0&navpanes=0`}
              className="mt-2 h-[28rem] w-full rounded-md border bg-white"
            />
          </details>
        )}
        {tex && (
          <details>
            <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">LaTeX source</summary>
            <pre className="mt-2 max-h-72 overflow-auto rounded-md bg-muted/50 p-3 text-xs">{tex}</pre>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

export default function Page() {
  const groups = resumesByCategory();
  const cats = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);

  return (
    <PageContainer
      title="Resumes by job category"
      description="Each job gets its own tailored resume (PDF for the form, LaTeX for Overleaf). Facts are validated against your profile, so nothing is invented."
    >
      {cats.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No tailored resumes yet. Run <code className="rounded bg-muted px-1.5 py-0.5">python -m applyforme run</code> (jobs scoring above your threshold get one).
          </CardContent>
        </Card>
      ) : (
        <Tabs defaultValue={cats[0]}>
          <TabsList className="h-auto! flex-wrap justify-start gap-1">
            {cats.map((c) => (
              <TabsTrigger key={c} value={c}>
                {c} <span className="tabular-nums opacity-60">{groups[c].length}</span>
              </TabsTrigger>
            ))}
          </TabsList>
          {cats.map((c) => (
            <TabsContent key={c} value={c}>
              <div className="grid gap-4 @3xl/main:grid-cols-2 @6xl/main:grid-cols-3">
                {groups[c].map((j) => (
                  <ResumeCard key={j.id} job={j} />
                ))}
              </div>
            </TabsContent>
          ))}
        </Tabs>
      )}
    </PageContainer>
  );
}
