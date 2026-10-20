import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { AppSidebar } from "@/components/app-sidebar";
import { PipelineBanner } from "@/components/pipeline-banner";
import { SiteHeader } from "@/components/site-header";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { auth, authDisabled } from "@/auth";
import { inboxCounts, listJobs, statusCounts } from "@/lib/db";
import { isOnboardingCompleteForSession } from "@/lib/onboarding-gate";
import { profileSummary } from "@/lib/profile";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = (await headers()).get("x-pathname") || "";
  const onOnboarding = pathname === "/onboarding" || pathname.startsWith("/onboarding/");
  const done = await isOnboardingCompleteForSession();

  // Each signed-in Google account must finish onboarding before other app pages.
  if (!onOnboarding && !done) {
    redirect("/onboarding");
  }

  if (onOnboarding) {
    return <div className="min-h-svh bg-background">{children}</div>;
  }

  const counts = statusCounts();
  const inboxTotal = Object.entries(inboxCounts()).filter(([k]) => k !== "submitted").reduce((a, [, n]) => a + n, 0);
  const jobsCount = listJobs({ status: ["new", "matched", "ready"], limit: 500 }).length;
  const session = await auth();
  const profile = profileSummary();
  const user = {
    name: session?.user?.name || profile.name,
    email: session?.user?.email || profile.email,
    image: session?.user?.image,
  };
  if (authDisabled() && !session?.user) {
    user.name = profile.name;
    user.email = profile.email || "local@localhost";
  }

  return (
    <SidebarProvider
      style={
        {
          "--sidebar-width": "calc(var(--spacing) * 72)",
          "--header-height": "calc(var(--spacing) * 12)",
        } as React.CSSProperties
      }
    >
      <AppSidebar
        variant="inset"
        user={user}
        feedbackCount={counts.needs_feedback ?? 0}
        inboxCount={inboxTotal}
        jobsCount={jobsCount}
      />
      <SidebarInset>
        <SiteHeader />
        <div className="pt-3">
          <PipelineBanner />
        </div>
        {children}
      </SidebarInset>
    </SidebarProvider>
  );
}
