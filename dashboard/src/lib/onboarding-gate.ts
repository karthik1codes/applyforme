import { redirect } from "next/navigation";
import { auth, authDisabled } from "@/auth";
import { loadProfile, profileOnboardingComplete } from "@/lib/profile";
import { markUserOnboardingComplete, userOnboardingDone } from "@/lib/users";

export function sessionUserId(session: { user?: { id?: string; email?: string | null } | null } | null): string {
  return (session?.user as { id?: string } | undefined)?.id || session?.user?.email || "local";
}

/**
 * Per-Gmail onboarding: each Google account must finish the wizard.
 * Global profile.yaml alone is not enough (another account may have completed it).
 */
export async function isOnboardingCompleteForSession(): Promise<boolean> {
  if (authDisabled()) {
    return profileOnboardingComplete();
  }
  const session = await auth();
  if (!session?.user?.email) return false;
  const userId = sessionUserId(session);
  if (userOnboardingDone(userId)) return true;

  // Legacy: yaml completed for this exact email → adopt for this user.
  try {
    const p = loadProfile();
    const yamlEmail = (p.personal?.email || "").trim().toLowerCase();
    const sessionEmail = session.user.email.trim().toLowerCase();
    if (yamlEmail && yamlEmail === sessionEmail && profileOnboardingComplete(p)) {
      markUserOnboardingComplete(userId, true);
      return true;
    }
  } catch {
    /* ignore */
  }
  return false;
}

/** Call from protected app pages so incomplete profiles finish the wizard first. */
export async function requireOnboarding() {
  if (!(await isOnboardingCompleteForSession())) redirect("/onboarding");
}
