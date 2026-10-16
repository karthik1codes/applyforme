import { NextResponse } from "next/server";
import { auth, authDisabled } from "@/auth";

const PROTECTED = [
  "/home",
  "/jobs",
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
];

export default auth((req) => {
  if (authDisabled()) return NextResponse.next();
  const path = req.nextUrl.pathname;
  const needsAuth = PROTECTED.some((p) => path === p || path.startsWith(p + "/"));
  if (needsAuth && !req.auth) {
    const url = new URL("/", req.nextUrl.origin);
    url.searchParams.set("next", path);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
});

export const config = {
  matcher: [
    "/home/:path*",
    "/jobs/:path*",
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
  ],
};
