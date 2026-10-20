"use client";

import { useState, type ComponentProps, type ReactNode } from "react";
import Link from "next/link";
import { useFormStatus } from "react-dom";
import { Loader2Icon, RefreshCwIcon, UnplugIcon } from "lucide-react";
import { disconnectLinkedInAction, refreshLinkedInAction } from "@/app/actions/linkedin";
import { Button } from "@/components/ui/button";

type ButtonVariant = ComponentProps<typeof Button>["variant"];
type ButtonSize = ComponentProps<typeof Button>["size"];

function PendingFormButton({
  children,
  pendingLabel,
  pendingMessage,
  icon,
  variant = "outline",
  size,
  className,
}: {
  children: ReactNode;
  pendingLabel: string;
  pendingMessage?: string;
  icon?: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
}) {
  const { pending } = useFormStatus();

  return (
    <>
      <Button type="submit" variant={variant} size={size} className={className} disabled={pending}>
        {pending ? <Loader2Icon className="animate-spin" aria-hidden /> : icon}
        {pending ? pendingLabel : children}
      </Button>
      {pending && pendingMessage ? (
        <span role="status" className="sr-only">
          {pendingMessage}
        </span>
      ) : null}
    </>
  );
}

/** Refresh, disconnect, and reconnect controls for a connected account. */
export function LinkedInActions() {
  const [confirming, setConfirming] = useState(false);

  return (
    <div className="flex flex-wrap items-center gap-2 sm:justify-end">
      {confirming ? (
        <>
          <span className="text-sm text-muted-foreground">Disconnect LinkedIn?</span>
          <form action={disconnectLinkedInAction} className="inline-flex">
            <PendingFormButton
              pendingLabel="Disconnecting…"
              pendingMessage="Disconnecting your LinkedIn account..."
              icon={<UnplugIcon aria-hidden />}
              variant="destructive"
            >
              Disconnect
            </PendingFormButton>
          </form>
          <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
            Cancel
          </Button>
        </>
      ) : (
        <>
          <form action={refreshLinkedInAction} className="inline-flex">
            <PendingFormButton
              pendingLabel="Refreshing…"
              pendingMessage="Refreshing your LinkedIn profile..."
              icon={<RefreshCwIcon aria-hidden />}
            >
              Refresh profile
            </PendingFormButton>
          </form>
          <Button type="button" variant="ghost" onClick={() => setConfirming(true)}>
            <UnplugIcon aria-hidden />
            Disconnect
          </Button>
          <Link
            href="/api/linkedin/connect"
            className="text-sm text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
          >
            Reconnect account
          </Link>
        </>
      )}
    </div>
  );
}

/** Submit button for the legacy-data cleanup form. */
export function RemoveLegacyDataButton() {
  return (
    <PendingFormButton pendingLabel="Removing…" pendingMessage="Removing old sign-in data..." size="sm">
      Remove
    </PendingFormButton>
  );
}
