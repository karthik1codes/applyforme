import Link from "next/link";
import { FindJobsButton } from "@/components/find-jobs-button";
import { PageContainer } from "@/components/page-container";
import { timeAgo } from "@/components/jobs-table";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { inbox, inboxCounts } from "@/lib/db";
import { cn } from "@/lib/utils";

const KINDS: { key: string; label: string; style: string }[] = [
  { key: "submitted", label: "Submitted", style: "bg-emerald-500/15 text-emerald-500" },
  { key: "confirmation", label: "Confirmations", style: "bg-sky-500/15 text-sky-500" },
  { key: "interview", label: "Interviews", style: "bg-violet-500/15 text-violet-500" },
  { key: "reply", label: "Replies", style: "bg-amber-500/15 text-amber-500" },
  { key: "rejection", label: "Rejections", style: "bg-destructive/15 text-destructive" },
];
const style = (k: string) => KINDS.find((x) => x.key === k)?.style ?? "";

export default async function Page({ searchParams }: { searchParams: Promise<{ kind?: string }> }) {
  const { kind } = await searchParams;
  const active = KINDS.some((k) => k.key === kind) ? kind : undefined;
  const counts = inboxCounts();
  const events = inbox(active);
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <PageContainer
      title="Applied inbox"
      description="Submissions and employer replies. Configure IMAP once in Settings / .env — then check inbox from here."
    >
      <div className="mb-3 flex justify-end">
        <FindJobsButton label="Check inbox now" stage="inbox" size="sm" variant="outline" />
      </div>
      <div className="flex flex-wrap gap-2">
        <Link href="/inbox" className={cn("rounded-full border px-3 py-1 text-sm", !active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>
          All <span className="tabular-nums opacity-70">{total}</span>
        </Link>
        {KINDS.map((k) => (
          <Link key={k.key} href={`/inbox?kind=${k.key}`} className={cn("rounded-full border px-3 py-1 text-sm", active === k.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>
            {k.label} <span className="tabular-nums opacity-70">{counts[k.key] ?? 0}</span>
          </Link>
        ))}
      </div>

      {events.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-10 text-center text-sm text-muted-foreground">
            <p>
              No messages yet. Submissions land here automatically. To pull employer emails, add IMAP credentials to your{" "}
              <code className="rounded bg-muted px-1">.env</code>, then tap Check inbox.
            </p>
            <FindJobsButton label="Check inbox now" stage="inbox" size="lg" variant="outline" />
          </CardContent>
        </Card>
      )}

      <div className="flex flex-col gap-2">
        {events.map((e) => (
          <Card key={e.id} size="sm">
            <CardContent>
              <details>
                <summary className="flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-1">
                  <Badge variant="secondary" className={style(e.kind)}>
                    {e.kind}
                  </Badge>
                  <Link href={`/applications/${encodeURIComponent(e.jobId)}`} className="font-medium hover:underline">
                    {e.company}
                  </Link>
                  <span className="text-sm text-muted-foreground">{e.jobTitle}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{timeAgo(e.createdAt)}</span>
                </summary>
                <div className="mt-3 space-y-2 text-sm">
                  <p className="font-medium">{e.title}</p>
                  {e.body && <pre className="whitespace-pre-wrap rounded-md bg-muted/50 p-3 font-sans text-muted-foreground">{e.body}</pre>}
                </div>
              </details>
            </CardContent>
          </Card>
        ))}
      </div>
    </PageContainer>
  );
}
