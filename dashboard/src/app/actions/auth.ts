"use server";

import { signIn, signOut } from "@/auth";

export async function googleSignIn(callbackUrl = "/onboarding") {
  await signIn("google", { redirectTo: callbackUrl });
}

export async function logout() {
  await signOut({ redirectTo: "/" });
}
