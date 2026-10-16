import { redirect } from "next/navigation";
import { auth, authDisabled } from "@/auth";
import { OnboardingWizard } from "@/components/onboarding-wizard";
import { loadProfile, onboardingDone } from "@/lib/profile";
import { upsertUser, userHasResume } from "@/lib/users";

export const dynamic = "force-dynamic";

export default async function OnboardingPage({
  searchParams,
}: {
  searchParams: Promise<{ resume?: string; force?: string }>;
}) {
  const sp = await searchParams;
  const session = await auth();
  if (!session?.user && !authDisabled()) redirect("/?next=/onboarding");

  const userId = (session?.user as { id?: string } | undefined)?.id || session?.user?.email || "local";
  if (session?.user?.email) {
    upsertUser({ id: userId, email: session.user.email, name: session.user.name, image: session.user.image });
  }
  if (onboardingDone() && sp.force !== "1") redirect("/home");

  const profile = loadProfile();
  const hasResume = userHasResume(userId);

  return <OnboardingWizard initial={profile} hasResume={hasResume} />;
}
