import { NextResponse } from "next/server";
import { auth, authDisabled } from "@/auth";

const PROTECTED = [
  "/home",
  "/jobs",
  "/internships",
  "/applications",
  "/feedback",
  "/inbox",
  "/ats",
  "/resumes",
  "/cover-letters",
  "/saved",
  "/preferences",
  "/interview",
  "/profile",
  "/settings",
  "/whatsapp",
  "/billing",
  "/onboarding",
  "/referral",
];

export default auth((req) => {
  const path = req.nextUrl.pathname;
  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-pathname", path);

  if (authDisabled()) {
    return NextResponse.next({ request: { headers: requestHeaders } });
  }

  const needsAuth = PROTECTED.some((p) => path === p || path.startsWith(p + "/"));
  if (needsAuth && !req.auth) {
    const url = new URL("/", req.nextUrl.origin);
    // After Google sign-in, always resume onboarding (not a random deep link).
    const next = path === "/onboarding" || path.startsWith("/onboarding")
      ? `${path}${req.nextUrl.search}`
      : "/onboarding";
    url.searchParams.set("next", next);
    return NextResponse.redirect(url);
  }
  return NextResponse.next({ request: { headers: requestHeaders } });
});

export const config = {
  matcher: [
    "/home/:path*",
    "/jobs/:path*",
    "/internships/:path*",
    "/applications/:path*",
    "/feedback/:path*",
    "/inbox/:path*",
    "/ats/:path*",
    "/resumes/:path*",
    "/cover-letters/:path*",
    "/saved/:path*",
    "/preferences/:path*",
    "/interview/:path*",
    "/profile/:path*",
    "/settings/:path*",
    "/whatsapp/:path*",
    "/billing/:path*",
    "/onboarding/:path*",
    "/referral/:path*",
  ],
};
