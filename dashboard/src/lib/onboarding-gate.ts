import { redirect } from "next/navigation";
import { onboardingDone } from "@/lib/profile";

/** Call from protected app pages so incomplete profiles finish the wizard first. */
export function requireOnboarding() {
  if (!onboardingDone()) redirect("/onboarding");
}
