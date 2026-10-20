import Link from "next/link";
import { PageContainer } from "@/components/page-container";
import { requireOnboarding } from "@/lib/onboarding-gate";
import { ensureInviteCode, loadProfile, saveProfile } from "@/lib/profile";
import { ReferralShare } from "@/components/referral-share";

export const dynamic = "force-dynamic";

export default async function ReferralPage({
  searchParams,
}: {
  searchParams: Promise<{ welcome?: string }>;
}) {
  await requireOnboarding();
  const { welcome } = await searchParams;
  const p = loadProfile();
  const code = ensureInviteCode(p);
  if (!p.attribution?.invite_code) {
    p.attribution = { ...(p.attribution || {}), invite_code: code };
    saveProfile(p);
  }

  const heard = p.attribution?.how_heard || p.screening?.how_did_you_hear || "—";
  const role = p.attribution?.role || "—";
  const usedCode = p.attribution?.referral_code || "";

  return (
    <PageContainer
      title={welcome ? "You're in" : "Refer friends"}
      description="Share your invite code. Friends enter it during onboarding."
    >
      {welcome ? (
        <p className="mb-6 text-sm text-emerald-600">
          Onboarding saved. Share your code, then open the dashboard to start applying.
        </p>
      ) : null}

      <div className="grid max-w-2xl gap-6">
        <div className="rounded-lg border bg-muted/30 p-5">
          <p className="text-sm text-muted-foreground">Your invite code</p>
          <p className="mt-1 font-mono text-2xl font-semibold tracking-wide">{code}</p>
          <ReferralShare code={code} />
        </div>

        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Heard about us</dt>
            <dd className="font-medium capitalize">{heard.replace(/_/g, " ")}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Your role</dt>
            <dd className="font-medium capitalize">{role.replace(/_/g, " ")}</dd>
          </div>
          {usedCode ? (
            <div className="sm:col-span-2">
              <dt className="text-muted-foreground">Referral you used</dt>
              <dd className="font-mono font-medium">{usedCode}</dd>
            </div>
          ) : null}
        </dl>

        <div className="flex flex-wrap gap-3">
          <Link
            href="/home?welcome=1"
            className="inline-flex min-h-10 items-center justify-center rounded-md bg-foreground px-4 py-2 text-sm text-background"
          >
            Go to dashboard
          </Link>
          <Link href="/jobs" className="inline-flex min-h-10 items-center justify-center rounded-md border px-4 py-2 text-sm">
            Browse jobs
          </Link>
        </div>
      </div>
    </PageContainer>
  );
}
