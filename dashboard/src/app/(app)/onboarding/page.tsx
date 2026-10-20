import { redirect } from "next/navigation";
import { auth, authDisabled } from "@/auth";
import { OnboardingWizard } from "@/components/onboarding-wizard";
import { isOnboardingCompleteForSession, sessionUserId } from "@/lib/onboarding-gate";
import { applySessionToProfile, loadProfile, saveProfile } from "@/lib/profile";
import { upsertUser, userHasResume } from "@/lib/users";

export const dynamic = "force-dynamic";

export default async function OnboardingPage({
  searchParams,
}: {
  searchParams: Promise<{ resume?: string; force?: string; ref?: string }>;
}) {
  const sp = await searchParams;
  const session = await auth();
  if (!session?.user && !authDisabled()) {
    const q = sp.ref ? `?ref=${encodeURIComponent(sp.ref)}` : "";
    redirect(`/?next=${encodeURIComponent(`/onboarding${q}`)}`);
  }

  const userId = sessionUserId(session);
  if (session?.user?.email) {
    upsertUser({ id: userId, email: session.user.email, name: session.user.name, image: session.user.image });
  }

  // This Google account already finished → referral (unless ?force=1).
  if ((await isOnboardingCompleteForSession()) && sp.force !== "1") redirect("/referral");

  const profile = loadProfile();
  // Bind yaml to this Gmail (switches identity if a different account signed in).
  if (applySessionToProfile(profile, session?.user)) {
    saveProfile(profile);
  }
  if (sp.ref && !profile.attribution?.referral_code) {
    profile.attribution = { ...(profile.attribution || {}), referral_code: sp.ref };
    saveProfile(profile);
  }
  const hasResume = userHasResume(userId) || sp.resume === "1";

  return (
    <OnboardingWizard
      initial={loadProfile()}
      hasResume={hasResume}
      startStep={sp.resume === "1" ? 3 : 0}
    />
  );
}
