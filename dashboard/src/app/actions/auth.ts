"use server";

import { signOut } from "@/auth";

/** End the session and send the user to the landing page Start applying CTA. */
export async function logout() {
  await signOut({ redirectTo: "/?signedout=1" });
}
