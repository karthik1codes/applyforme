import Link from "next/link";
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  CircleAlertIcon,
  InfoIcon,
} from "lucide-react";
import { deleteLegacyLinkedInFileAction } from "@/app/actions/linkedin";
import { LinkedInActions, RemoveLegacyDataButton } from "@/components/linkedin-actions";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { LinkedInCardData, LinkedInConnection } from "@/lib/linkedin";

const NOTICES: Record<string, { tone: "ok" | "warn" | "error"; text: string }> = {
  connected: { tone: "ok", text: "LinkedIn is connected." },
  disconnected: { tone: "ok", text: "LinkedIn is disconnected. You can also remove access from your LinkedIn settings." },
  refreshed: { tone: "ok", text: "Your LinkedIn profile is up to date." },
  denied: { tone: "warn", text: "LinkedIn sign-in was cancelled. Nothing was connected." },
  error: { tone: "error", text: "Unable to connect to LinkedIn. Please try again." },
  refresh_error: { tone: "error", text: "We couldn't refresh your LinkedIn profile. Please try again." },
  legacy_deleted: { tone: "ok", text: "Old sign-in data was removed." },
  legacy_missing: { tone: "ok", text: "No old sign-in data was found." },
};

function LinkedInGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={className}>
      <path d="M20.45 20.45h-3.55v-5.57c0-1.33-.03-3.04-1.85-3.04-1.86 0-2.14 1.45-2.14 2.94v5.67H9.36V9h3.41v1.56h.05c.47-.9 1.63-1.85 3.36-1.85 3.6 0 4.27 2.37 4.27 5.45v6.29zM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12zM7.12 20.45H3.56V9h3.56v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.72v20.56C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.72V1.72C24 .77 23.2 0 22.22 0z" />
    </svg>
  );
}

function ProfileAvatar({ connection }: { connection: LinkedInConnection }) {
  if (connection.picture) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={connection.picture}
        alt=""
        className="size-10 shrink-0 rounded-full object-cover ring-1 ring-border"
      />
    );
  }

  const initials = (connection.displayName || connection.email || "LinkedIn member").slice(0, 2).toUpperCase();
  return (
    <span
      aria-hidden="true"
      className="flex size-10 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium text-muted-foreground ring-1 ring-border"
    >
      {initials}
    </span>
  );
}

function StatusBadge({ connected }: { connected: boolean }) {
  if (!connected) {
    return (
      <Badge variant="outline" className="shrink-0 text-muted-foreground">
        Not connected
      </Badge>
    );
  }

  return (
    <Badge
      variant="outline"
      className="shrink-0 gap-1.5 border-emerald-600/20 bg-emerald-500/10 text-emerald-700 dark:border-emerald-400/20 dark:text-emerald-300"
    >
      <span aria-hidden="true" className="size-1.5 rounded-full bg-emerald-500" />
      Connected
    </Badge>
  );
}

export function LinkedInConnectorCard({ data, notice }: { data: LinkedInCardData; notice?: string }) {
  const n = notice ? NOTICES[notice] : undefined;
  const connection = data.connection;
  const connected = Boolean(connection);
  const description = connected
    ? "Your LinkedIn account is connected. You can manage your connection and keep your profile information up to date."
    : "Connect your LinkedIn account to link it with your workspace.";

  const noticeTone =
    n?.tone === "error"
      ? "text-destructive"
      : n?.tone === "warn"
        ? "text-amber-700 dark:text-amber-300"
        : "text-emerald-700 dark:text-emerald-300";
  const NoticeIcon = n?.tone === "error" ? CircleAlertIcon : n?.tone === "warn" ? AlertTriangleIcon : CheckCircle2Icon;

  return (
    <Card className="mx-auto w-full max-w-3xl">
      <CardHeader className="gap-1.5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border bg-muted/40 text-[#0a66c2] dark:text-[#70b5f9]">
              <LinkedInGlyph className="size-4" />
            </span>
            <CardTitle>LinkedIn</CardTitle>
          </div>
          <StatusBadge connected={connected} />
        </div>
        <CardDescription>{description}</CardDescription>
      </CardHeader>

      <CardContent className="space-y-5 text-sm">
        {data.configured && n && (
          <p role="status" className={cn("flex items-start gap-2", noticeTone)}>
            <NoticeIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span>{n.text}</span>
          </p>
        )}

        {!data.configured && (
          <p className="flex items-start gap-2 text-muted-foreground">
            <InfoIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span>LinkedIn isn&apos;t available on this workspace right now. Please try again later.</span>
          </p>
        )}

        {data.configured && !data.signedIn && (
          <p className="flex items-start gap-2 text-muted-foreground">
            <InfoIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span>Sign in to connect your LinkedIn account.</span>
          </p>
        )}

        {data.configured && data.signedIn && connection && (
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-center gap-3">
              <ProfileAvatar connection={connection} />
              <div className="min-w-0">
                <p className="truncate font-medium">{connection.displayName || "LinkedIn member"}</p>
                {connection.email && <p className="truncate text-sm text-muted-foreground">{connection.email}</p>}
                <p className="mt-0.5 text-xs text-muted-foreground">Connected account</p>
              </div>
            </div>
            <LinkedInActions />
          </div>
        )}

        {data.configured && data.signedIn && connection && connection.expired && (
          <p className="flex items-start gap-2 text-sm text-amber-700 dark:text-amber-300">
            <AlertTriangleIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span>Your LinkedIn connection needs to be renewed. Reconnect your account to continue.</span>
          </p>
        )}

        {data.configured && data.signedIn && connection?.lastError && !n && (
          <p role="status" className="flex items-start gap-2 text-sm text-destructive">
            <CircleAlertIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span>Unable to connect to LinkedIn. Please try again.</span>
          </p>
        )}

        {data.configured && data.signedIn && !connection && (
          <Link href="/api/linkedin/connect" className={buttonVariants({ className: "w-full sm:w-fit" })}>
            <LinkedInGlyph className="size-3.5" />
            Connect LinkedIn
          </Link>
        )}

        {data.legacyFileExists && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2.5">
            <div className="flex items-start gap-2">
              <AlertTriangleIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
              <div>
                <p className="text-sm font-medium">Old sign-in data found</p>
                <p className="text-xs text-muted-foreground">
                  A password saved by an earlier version is still stored on this server.
                </p>
              </div>
            </div>
            <form action={deleteLegacyLinkedInFileAction}>
              <RemoveLegacyDataButton />
            </form>
          </div>
        )}

        <p className="flex items-start gap-2 text-xs text-muted-foreground">
          <InfoIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
          <span>
            Your LinkedIn connection keeps your account linked to this workspace. Job applications may still require you
            to review details and complete certain steps yourself.
          </span>
        </p>
      </CardContent>
    </Card>
  );
}
