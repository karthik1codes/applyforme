import Link from "next/link";
import { FindJobsButton } from "@/components/find-jobs-button";
import { PageContainer } from "@/components/page-container";
import { ResumeEditor } from "@/components/resume-editor";
import { OverleafButton, ResumeLinks } from "@/components/resume-actions";
import { ResumePdfViewer } from "@/components/resume-pdf-viewer";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { resumesByCategory, type Job } from "@/lib/db";
import { readOutput } from "@/lib/files";
import { loadProfile } from "@/lib/profile";
import { profileToResumeDoc } from "@/lib/resume-doc";

function ResumeCard({ job }: { job: Job }) {
  const tex = readOutput(job.resumeTex);
  const pdfName = `${job.company}-${job.title}`.replace(/[^\w-]+/g, "-").slice(0, 60);
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
          {tex && <OverleafButton tex={tex} name={pdfName} />}
          <Link
            href="/resumes?tab=editor"
            className="text-xs text-muted-foreground underline-offset-2 hover:underline"
          >
            Edit master template
          </Link>
        </div>
        {job.resumePdf && (
          <details open>
            <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">Preview PDF</summary>
            <ResumePdfViewer
              title={`${job.company} resume`}
              src={`/api/files/${encodeURIComponent(job.resumePdf)}`}
              filename={`${pdfName}.pdf`}
            />
          </details>
        )}
        {tex && (
          <details>
            <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">LaTeX source</summary>
            <div className="mt-2 flex justify-end">
              <a
                href={`/api/files/${encodeURIComponent(job.resumeTex!)}?download`}
                className="text-xs text-muted-foreground underline-offset-2 hover:underline"
              >
                Download .tex
              </a>
            </div>
            <pre className="mt-2 max-h-72 overflow-auto rounded-md bg-muted/50 p-3 text-xs">{tex}</pre>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

export default async function Page({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab } = await searchParams;
  const defaultTab = tab === "jobs" ? "jobs" : "editor";
  const groups = resumesByCategory();
  const cats = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);
  const master = profileToResumeDoc(loadProfile());

  return (
    <PageContainer
      title="Resumes"
      description="Edit your academic resume master template, then review per-job tailored PDFs agents generate from it."
    >
      <Tabs defaultValue={defaultTab}>
        <TabsList>
          <TabsTrigger value="editor">Resume editor</TabsTrigger>
          <TabsTrigger value="jobs">
            Tailored by job
            {cats.length > 0 && <span className="ml-1 tabular-nums opacity-60">{cats.reduce((n, c) => n + groups[c].length, 0)}</span>}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="editor" className="mt-4">
          <ResumeEditor initial={master} />
        </TabsContent>

        <TabsContent value="jobs" className="mt-4 space-y-4">
          {cats.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-4 py-10 text-center text-sm text-muted-foreground">
                <p>
                  No tailored resumes yet. Edit your master template above, then find jobs — roles above your match
                  threshold get an Elegant Resume PDF automatically.
                </p>
                <FindJobsButton label="Find jobs for me" size="lg" />
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
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}
