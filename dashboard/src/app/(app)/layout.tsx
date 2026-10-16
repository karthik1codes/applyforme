import { AppSidebar } from "@/components/app-sidebar";
import { SiteHeader } from "@/components/site-header";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { auth, authDisabled } from "@/auth";
import { inboxCounts, listJobs, statusCounts } from "@/lib/db";
import { profileSummary } from "@/lib/profile";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
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
        {children}
      </SidebarInset>
    </SidebarProvider>
  );
}
