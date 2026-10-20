import Link from "next/link";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Job } from "@/lib/db";

export function timeAgo(iso: string | null): string {
  if (!iso) return "-";
  const s = Math.max(1, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 3600) return `${Math.round(s / 60) || 1}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

export function JobsTable({ jobs, empty = "Nothing here yet." }: { jobs: Job[]; empty?: string }) {
  if (!jobs.length) return <p className="py-10 text-center text-sm text-muted-foreground">{empty}</p>;
  return (
    <div className="overflow-hidden rounded-lg border">
      <Table>
        <TableHeader className="bg-muted">
          <TableRow>
            <TableHead className="w-16">Match</TableHead>
            <TableHead>Role</TableHead>
            <TableHead className="hidden md:table-cell">Links</TableHead>
            <TableHead className="hidden lg:table-cell">Category</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="hidden xl:table-cell text-right">Updated</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.map((j) => (
            <TableRow key={j.id}>
              <TableCell className="font-semibold tabular-nums">{j.score ?? "-"}</TableCell>
              <TableCell className="max-w-[28rem]">
                <Link href={`/applications/${encodeURIComponent(j.id)}`} className="font-medium hover:underline">
                  {j.title}
                </Link>
                <div className="truncate text-xs text-muted-foreground">
                  {j.company}
                  {j.location ? ` · ${j.location}` : ""}
                </div>
              </TableCell>
              <TableCell className="hidden md:table-cell">
                <div className="flex flex-col gap-0.5 text-xs">
                  <a href={j.applyUrl || j.url} target="_blank" rel="noreferrer" className="text-sky-600 hover:underline dark:text-sky-400">
                    Posting
                  </a>
                  {j.careersUrl ? (
                    <a href={j.careersUrl} target="_blank" rel="noreferrer" className="text-muted-foreground hover:underline">
                      Careers
                    </a>
                  ) : j.companyWebsite ? (
                    <a href={j.companyWebsite} target="_blank" rel="noreferrer" className="text-muted-foreground hover:underline">
                      Company
                    </a>
                  ) : null}
                </div>
              </TableCell>
              <TableCell className="hidden lg:table-cell">
                <Badge variant="outline">{j.category}</Badge>
              </TableCell>
              <TableCell>
                <StatusBadge status={j.status} />
              </TableCell>
              <TableCell className="hidden xl:table-cell text-right text-muted-foreground">{timeAgo(j.appliedAt ?? j.updatedAt)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
