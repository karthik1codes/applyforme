"use client";

import { usePathname } from "next/navigation";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";

const TITLES: [string, string][] = [
  ["/onboarding", "Onboarding"],
  ["/jobs", "Jobs"],
  ["/applications", "Applications"],
  ["/feedback", "Feedback"],
  ["/inbox", "Inbox"],
  ["/ats", "ATS Score"],
  ["/resumes", "Resumes"],
  ["/cover-letters", "Cover Letters"],
  ["/saved", "Saved Jobs"],
  ["/preferences", "Preferences"],
  ["/interview", "AI Interview Assistant"],
  ["/profile", "Profile"],
  ["/billing", "Billing"],
  ["/settings", "Settings"],
  ["/whatsapp", "WhatsApp"],
  ["/home", "Dashboard"],
];

export function SiteHeader() {
  const path = usePathname();
  const title = TITLES.find(([p]) => path.startsWith(p))?.[1] ?? "Dashboard";
  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full items-center gap-1 px-4 lg:gap-2 lg:px-6">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mx-2 h-4 data-vertical:self-auto" />
        <h1 className="text-base font-medium">{title}</h1>
      </div>
    </header>
  );
}
