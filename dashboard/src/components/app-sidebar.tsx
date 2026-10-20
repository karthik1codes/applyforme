"use client";

import Link from "next/link";
import {
  BookmarkIcon,
  BriefcaseBusinessIcon,
  CreditCardIcon,
  GiftIcon,
  FilePenLineIcon,
  FileTextIcon,
  GaugeIcon,
  InboxIcon,
  LayoutDashboardIcon,
  ListChecksIcon,
  MessageSquareIcon,
  MicIcon,
  SearchIcon,
  Settings2Icon,
  SettingsIcon,
  SlidersHorizontalIcon,
  GraduationCapIcon,
  UserIcon,
} from "lucide-react";

import { NavSection } from "@/components/nav-section";
import { NavUser } from "@/components/nav-user";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

export function AppSidebar({
  user,
  feedbackCount,
  inboxCount,
  jobsCount,
  ...props
}: React.ComponentProps<typeof Sidebar> & {
  user: { name: string; email: string; image?: string | null };
  feedbackCount: number;
  inboxCount: number;
  jobsCount: number;
}) {
  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton className="data-[slot=sidebar-menu-button]:p-1.5!" render={<Link href="/home" />}>
              <BriefcaseBusinessIcon className="size-5!" />
              <span className="text-base font-semibold">applyforme</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavSection
          label="Auto apply"
          items={[
            { title: "Dashboard", url: "/home", icon: <LayoutDashboardIcon /> },
            { title: "Jobs", url: "/jobs", icon: <SearchIcon />, badge: jobsCount || undefined },
            { title: "Internships", url: "/internships", icon: <GraduationCapIcon /> },
            { title: "Applications", url: "/applications", icon: <ListChecksIcon /> },
            { title: "Inbox", url: "/inbox", icon: <InboxIcon />, badge: inboxCount || undefined },
          ]}
        />
        <NavSection
          label="Documents"
          items={[
            { title: "ATS Score", url: "/ats", icon: <GaugeIcon /> },
            { title: "Resumes", url: "/resumes", icon: <FileTextIcon /> },
            { title: "Cover Letters", url: "/cover-letters", icon: <FilePenLineIcon /> },
          ]}
        />
        <NavSection
          label="More"
          items={[
            { title: "Saved Jobs", url: "/saved", icon: <BookmarkIcon /> },
            { title: "Preferences", url: "/preferences", icon: <SlidersHorizontalIcon /> },
            { title: "AI Interview Assistant", url: "/interview", icon: <MicIcon />, popular: true },
          ]}
        />
        <NavSection
          label="Account"
          items={[
            { title: "Profile", url: "/profile", icon: <UserIcon /> },
            { title: "Referral", url: "/referral", icon: <GiftIcon /> },
            { title: "Billing", url: "/billing", icon: <CreditCardIcon /> },
            { title: "Settings", url: "/settings", icon: <SettingsIcon /> },
            { title: "Feedback", url: "/feedback", icon: <MessageSquareIcon />, badge: feedbackCount || undefined },
            { title: "WhatsApp", url: "/whatsapp", icon: <Settings2Icon /> },
          ]}
        />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={user} />
      </SidebarFooter>
    </Sidebar>
  );
}
