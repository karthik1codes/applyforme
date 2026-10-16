import Link from "next/link";
import { skipJob, submitAnswers } from "@/app/actions";
import { PageContainer } from "@/components/page-container";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { feedbackQueue, type Question } from "@/lib/db";

const selectCls =
  "h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

function Field({ q }: { q: Question }) {
  const name = `q_${q.id}`;
  const initial = q.answer ?? q.suggested ?? "";
  return (
    <div className="space-y-1.5">
      <Label htmlFor={name}>{q.label}</Label>
      {q.options.length > 0 ? (
        <select id={name} name={name} defaultValue={initial} className={selectCls}>
          <option value="">Choose...</option>
          {q.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      ) : q.label.length > 60 || q.type === "textarea" ? (
        <Textarea id={name} name={name} defaultValue={initial} rows={4} />
      ) : (
        <Input id={name} name={name} defaultValue={initial} />
      )}
      {q.suggested && !q.answer && <p className="text-xs text-muted-foreground">Agent suggestion pre-filled; check it before saving.</p>}
    </div>
  );
}

export default function Page() {
  const queue = feedbackQueue();
  return (
    <PageContainer
      title="Applications that need your feedback"
      description="The agent stopped before filling these forms because it could not answer a required question from your profile (it never guesses)."
    >
      {queue.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">All clear. Nothing is waiting on you.</CardContent>
        </Card>
      )}
      {queue.map(({ job, questions }) => (
        <Card key={job.id}>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <CardTitle>
                  <Link href={`/applications/${encodeURIComponent(job.id)}`} className="hover:underline">
                    {job.title}
                  </Link>
                </CardTitle>
                <CardDescription>
                  {job.company} · <Badge variant="outline">{job.category}</Badge>
                </CardDescription>
              </div>
              <form action={skipJob.bind(null, job.id)}>
                <Button type="submit" variant="ghost" size="sm">
                  Skip this job
                </Button>
              </form>
            </div>
          </CardHeader>
          <CardContent>
            <form action={submitAnswers.bind(null, job.id)} className="space-y-4">
              {questions.map((q) => (
                <Field key={q.id} q={q} />
              ))}
              <div className="flex flex-wrap items-center gap-3">
                <Button type="submit">Save answers</Button>
                <span className="text-xs text-muted-foreground">
                  Then run <code className="rounded bg-muted px-1.5 py-0.5">python -m applyforme apply {job.id}</code> to fill and submit.
                </span>
              </div>
            </form>
          </CardContent>
        </Card>
      ))}
    </PageContainer>
  );
}
