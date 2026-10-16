import { Badge } from "@/components/ui/badge";
import type { Status } from "@/lib/db";

const LABEL: Record<string, string> = {
  new: "New", matched: "Matched", skipped: "Skipped", ready: "Ready to apply",
  needs_feedback: "Needs feedback", manual: "Apply manually", applied: "Applied", failed: "Failed",
};

const STYLE: Record<string, string> = {
  applied: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  ready: "bg-sky-500/15 text-sky-600 dark:text-sky-400",
  needs_feedback: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  manual: "bg-orange-500/15 text-orange-600 dark:text-orange-400",
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
