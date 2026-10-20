import { NextResponse } from "next/server";
import {
  connectLinkedInFromCode,
  consumeLinkedInState,
  currentLinkedInUserId,
  linkedinConfigError,
} from "@/lib/linkedin";

function back(request: Request, params: Record<string, string>) {
  const url = new URL("/settings", request.url);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  return NextResponse.redirect(url);
}

export async function GET(request: Request) {
  const userId = await currentLinkedInUserId();
  if (!userId) return back(request, { linkedin: "signin" });
  const configError = linkedinConfigError();
  if (configError) return back(request, { linkedin: "not_configured", reason: configError });

  const url = new URL(request.url);
  const state = url.searchParams.get("state") || "";
  // Consume first: an error response or a replayed callback must not be reusable.
  const stateOk = consumeLinkedInState(state, userId);
  if (!stateOk) {
    return back(request, { linkedin: "error", reason: "Sign-in state was invalid, expired, or already used." });
  }

  const oauthError = url.searchParams.get("error");
  if (oauthError) {
    const detail = url.searchParams.get("error_description") || oauthError;
    return back(request, { linkedin: "denied", reason: detail.slice(0, 200) });
  }

  const code = url.searchParams.get("code") || "";
  if (!code) return back(request, { linkedin: "error", reason: "LinkedIn did not return an authorization code." });

  try {
    await connectLinkedInFromCode(userId, code);
    return back(request, { linkedin: "connected" });
  } catch (e) {
    const reason = e instanceof Error ? e.message : "LinkedIn sign-in failed";
    return back(request, { linkedin: "error", reason: reason.slice(0, 240) });
  }
}
