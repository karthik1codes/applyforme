import Link from "next/link";
import { notFound } from "next/navigation";
import { ApplyLiveViewer } from "@/components/apply-live-viewer";
import { ApplyReviewCard } from "@/components/apply-review-card";
import { TailorJobButton } from "@/components/tailor-job-button";
import { PageContainer } from "@/components/page-container";
import { JobLinks } from "@/components/job-links";
import { OverleafButton, ResumeLinks } from "@/components/resume-actions";
import { ResumePdfViewer } from "@/components/resume-pdf-viewer";
import { StatusBadge } from "@/components/status-badge";
import { timeAgo } from "@/components/jobs-table";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getApplySession, getJob, jobEvents, questionsFor } from "@/lib/db";
import { readOutput } from "@/lib/files";

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ applying?: string }>;
}) {
  const { id } = await params;
  const { applying } = await searchParams;
  const job = getJob(decodeURIComponent(id));
  if (!job) notFound();
  const events = jobEvents(job.id);
  const questions = questionsFor(job.id);
  const applySession = getApplySession(job.id);
  const tex = readOutput(job.resumeTex);
  const applyStatuses = [
    "ready", "matched", "manual", "failed", "blocked", "cancelled",
    "in_progress", "awaiting_review", "applied",
  ];
  const showApplyCard = !!job.coverLetter && applyStatuses.includes(job.status);
  const almostReady = ["matched", "ready", "manual"].includes(job.status) && !job.coverLetter;

  return (
    <PageContainer>
      {applying && (
        <p className="rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-sm text-sky-800 dark:text-sky-200">
          The agent is preparing the form in a real Chromium window. It will stop for your review — nothing is
          submitted until you press <span className="font-medium">Submit application</span>.
        </p>
      )}
      <ApplyLiveViewer jobId={job.id} force={!!applying} />
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
          <JobLinks
            url={job.url}
            applyUrl={job.applyUrl}
            careersUrl={job.careersUrl}
            companyWebsite={job.companyWebsite}
            companyLinkedin={job.companyLinkedin}
          />
          <ResumeLinks pdf={job.resumePdf} tex={job.resumeTex} />
          {tex && <OverleafButton tex={tex} name={`${job.company}-${job.title}`.replace(/[^\w-]+/g, "-").slice(0, 60)} />}
          {almostReady && (
            <div className="flex flex-col items-end gap-2">
              <span
                className={buttonVariants({ size: "sm", variant: "secondary" }) + " pointer-events-none opacity-60"}
                title="Needs a tailored resume + cover letter first"
              >
                Apply with agent
              </span>
              <TailorJobButton jobId={job.id} />
            </div>
          )}
          {job.status === "needs_feedback" && (
            <Link className={buttonVariants({ size: "sm" })} href="/feedback">
              Answer questions
            </Link>
          )}
        </div>
      </div>

      {showApplyCard && (
        <ApplyReviewCard
          jobId={job.id}
          status={job.status}
          hasCoverLetter={!!job.coverLetter}
          initialState={applySession?.state ?? null}
          confirmation={applySession?.confirmation ?? null}
          submitAttempted={!!applySession?.submitAttemptedAt}
          lastError={applySession?.lastError ?? ""}
        />
      )}

      {job.notes && <p className="rounded-md border bg-muted/40 p-3 text-sm">{job.notes}</p>}

      {(job.resumePdf || job.coverLetter) && (
        <Card>
          <CardHeader>
            <CardTitle>Tailored resume</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {job.resumePdf ? (
              <ResumePdfViewer
                title={`${job.company} resume`}
                src={`/api/files/${encodeURIComponent(job.resumePdf)}`}
                filename={`${job.company}-${job.title}`.replace(/[^\w-]+/g, "-").slice(0, 60) + ".pdf"}
              />
            ) : (
              <p className="text-sm text-muted-foreground">Cover letter ready — resume PDF missing. Run Tailor again.</p>
            )}
          </CardContent>
        </Card>
      )}

      {(job.companyWebsite || job.careersUrl || job.companyInfo?.industry) && (
        <Card>
          <CardHeader>
            <CardTitle>Company (Crustdata)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {job.companyInfo?.description && <p className="text-muted-foreground">{job.companyInfo.description}</p>}
            <dl className="grid gap-1 sm:grid-cols-2">
              {job.companyInfo?.industry && (
                <>
                  <dt className="text-muted-foreground">Industry</dt>
                  <dd>{job.companyInfo.industry}</dd>
                </>
              )}
              {job.companyInfo?.employee_count != null && (
                <>
                  <dt className="text-muted-foreground">Headcount</dt>
                  <dd>{job.companyInfo.employee_count}</dd>
                </>
              )}
              {job.companyInfo?.openings_count != null && (
                <>
                  <dt className="text-muted-foreground">Open roles</dt>
                  <dd>{job.companyInfo.openings_count}</dd>
                </>
              )}
              {job.companyInfo?.funding_stage && (
                <>
                  <dt className="text-muted-foreground">Funding</dt>
                  <dd>{job.companyInfo.funding_stage}</dd>
                </>
              )}
            </dl>
            <p className="break-all text-xs text-muted-foreground">
              Posting:{" "}
              <a className="underline" href={job.applyUrl || job.url} target="_blank" rel="noreferrer">
                {job.applyUrl || job.url}
              </a>
            </p>
            {job.careersUrl && (
              <p className="break-all text-xs text-muted-foreground">
                Careers:{" "}
                <a className="underline" href={job.careersUrl} target="_blank" rel="noreferrer">
                  {job.careersUrl}
                </a>
              </p>
            )}
          </CardContent>
        </Card>
      )}

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
