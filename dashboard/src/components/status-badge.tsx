import { Badge } from "@/components/ui/badge";
import type { Status } from "@/lib/db";

const LABEL: Record<string, string> = {
  new: "New", matched: "Matched", skipped: "Skipped", ready: "Ready to prepare",
  needs_feedback: "Needs feedback", manual: "Needs you", applied: "Applied", failed: "Failed",
  in_progress: "Preparing", awaiting_review: "Awaiting your review", blocked: "Blocked", cancelled: "Cancelled",
};

const STYLE: Record<string, string> = {
  applied: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  ready: "bg-sky-500/15 text-sky-600 dark:text-sky-400",
  in_progress: "bg-sky-500/15 text-sky-600 dark:text-sky-400",
  awaiting_review: "bg-indigo-500/15 text-indigo-600 dark:text-indigo-400",
  needs_feedback: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  manual: "bg-orange-500/15 text-orange-600 dark:text-orange-400",
  blocked: "bg-orange-500/15 text-orange-600 dark:text-orange-400",
  cancelled: "bg-muted text-muted-foreground",
  matched: "bg-violet-500/15 text-violet-600 dark:text-violet-400",
  failed: "bg-destructive/15 text-destructive",
};

export function StatusBadge({ status }: { status: Status | string }) {
  return (
    <Badge variant="secondary" className={STYLE[status] ?? ""}>
      {LABEL[status] ?? status}
    </Badge>
  );
}
