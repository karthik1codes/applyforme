import { handlers } from "@/auth";
import { NextRequest, NextResponse } from "next/server";

const { GET: authGet, POST: authPost } = handlers;

function appOrigin(req: NextRequest): string {
  const fromEnv = (process.env.AUTH_URL || process.env.NEXTAUTH_URL || process.env.APP_URL || "").replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  return req.nextUrl.origin;
}

/**
 * Bare /api/auth/callback/google (no ?code=&iss=) used to throw
 * OperationProcessingError: response parameter "iss" (issuer) missing → Configuration.
 * Prefetch / stale tabs hit that URL; send them home instead.
 */
export async function GET(req: NextRequest) {
  const path = req.nextUrl.pathname;
  const isGoogleCallback = path === "/api/auth/callback/google" || path.endsWith("/callback/google");
  if (isGoogleCallback) {
    const code = req.nextUrl.searchParams.get("code");
    const oauthError = req.nextUrl.searchParams.get("error");
    if (!code && !oauthError) {
      return NextResponse.redirect(new URL("/", appOrigin(req)));
    }
  }
  return authGet(req);
}

export async function POST(req: NextRequest) {
  return authPost(req);
}
