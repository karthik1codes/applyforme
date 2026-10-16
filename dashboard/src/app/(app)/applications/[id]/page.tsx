import Link from "next/link";
import { notFound } from "next/navigation";
import { PageContainer } from "@/components/page-container";
import { OverleafButton, ResumeLinks } from "@/components/resume-actions";
import { StatusBadge } from "@/components/status-badge";
import { timeAgo } from "@/components/jobs-table";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getJob, jobEvents, questionsFor } from "@/lib/db";
import { readOutput } from "@/lib/files";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const job = getJob(decodeURIComponent(id));
  if (!job) notFound();
  const events = jobEvents(job.id);
  const questions = questionsFor(job.id);
  const tex = readOutput(job.resumeTex);

  return (
    <PageContainer>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">{job.title}</h2>
          <p className="text-sm text-muted-foreground">
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusBadge status={job.status} />
            <Badge variant="outline">{job.category}</Badge>
            {job.score !== null && <Badge variant="secondary">Match {job.score}/100</Badge>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <a className={buttonVariants({ variant: "outline", size: "sm" })} href={job.url} target="_blank" rel="noreferrer">
            Job posting
          </a>
          <ResumeLinks pdf={job.resumePdf} tex={job.resumeTex} />
          {tex && <OverleafButton tex={tex} name={`${job.company}-${job.title}`.replace(/[^\w-]+/g, "-").slice(0, 60)} />}
          {job.status === "needs_feedback" && (
            <Link className={buttonVariants({ size: "sm" })} href="/feedback">
              Answer questions
            </Link>
          )}
        </div>
      </div>

      {job.notes && <p className="rounded-md border bg-muted/40 p-3 text-sm">{job.notes}</p>}

      <div className="grid gap-4 @3xl/main:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Why this score</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <ul className="list-disc space-y-1 pl-5">{job.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
            {job.redFlags.length > 0 && (
              <>
                <p className="font-medium text-amber-500">Red flags</p>
                <ul className="list-disc space-y-1 pl-5">{job.redFlags.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </>
            )}
            {!job.reasons.length && <p className="text-muted-foreground">Not scored yet.</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Timeline</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {events.length === 0 && <p className="text-muted-foreground">No activity yet.</p>}
            {events.map((e) => (
              <div key={e.id} className="border-l-2 pl-3">
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{e.kind}</Badge>
                  <span className="text-xs text-muted-foreground">{timeAgo(e.createdAt)}</span>
                </div>
                <p className="mt-1">{e.title}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {questions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Screening questions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {questions.map((q) => (
              <div key={q.id}>
                <p className="font-medium">{q.label}</p>
                <p className="text-muted-foreground">{q.answer ?? "Unanswered"}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {job.coverLetter && (
        <Card>
          <CardHeader>
            <CardTitle>Cover letter</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{job.coverLetter}</pre>
          </CardContent>
        </Card>
      )}
    </PageContainer>
  );
}
