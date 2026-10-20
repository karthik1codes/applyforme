import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Card, CardAction, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import type { overview } from "@/lib/db"

type Overview = ReturnType<typeof overview>

function Kpi({ label, value, badge, line, sub, href }: { label: string; value: React.ReactNode; badge?: string; line: string; sub: string; href: string }) {
  return (
    <Card className="@container/card">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
          <Link href={href}>{value}</Link>
        </CardTitle>
        {badge && (
          <CardAction>
            <Badge variant="outline">{badge}</Badge>
          </CardAction>
        )}
      </CardHeader>
      <CardFooter className="flex-col items-start gap-1.5 text-sm">
        <div className="line-clamp-1 font-medium">{line}</div>
        <div className="text-muted-foreground">{sub}</div>
      </CardFooter>
    </Card>
  )
}

export function SectionCards({ o }: { o: Overview }) {
  return (
    <div className="grid grid-cols-1 gap-4 px-4 *:data-[slot=card]:bg-linear-to-t *:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card *:data-[slot=card]:shadow-xs lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4 dark:*:data-[slot=card]:bg-card">
      <Kpi label="Jobs applied" value={o.applied} badge={`+${o.appliedToday} today`} line={`${o.appliedWeek} in the last 7 days`} sub="Submitted applications" href="/applications" />
      <Kpi label="Needs your feedback" value={o.needsFeedback} badge={o.needsFeedback ? "action" : "clear"} line={o.needsFeedback ? "Agents are waiting on you" : "Nothing blocked"} sub="Required questions the agent couldn't answer" href="/feedback" />
      <Kpi label="Awaiting your review" value={o.awaitingReview} line={o.awaitingReview ? "Form filled — check it, then submit" : "Nothing waiting on you"} sub="Open a role → review and submit" href="/applications?status=review" />
      <Kpi label="Average match score" value={o.avgScore || "-"} badge={`${o.total} jobs`} line="Across all scored jobs" sub={`${o.replies} employer repl${o.replies === 1 ? "y" : "ies"} tracked`} href="/inbox" />
    </div>
  )
}
