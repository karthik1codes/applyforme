"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

export type NavItem = {
  title: string;
  url: string;
  icon?: React.ReactNode;
  badge?: number | string;
  popular?: boolean;
};

export function NavSection({ label, items }: { label: string; items: NavItem[] }) {
  const path = usePathname();
  const active = (url: string) => path === url || (url !== "/home" && path.startsWith(url));
  return (
    <SidebarGroup>
      <SidebarGroupLabel className="text-[11px] font-medium tracking-wider text-muted-foreground/80 uppercase">
        {label}
      </SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => (
            <SidebarMenuItem key={item.url}>
              <SidebarMenuButton tooltip={item.title} isActive={active(item.url)} render={<Link href={item.url} />}>
                {item.icon}
                <span>{item.title}</span>
              </SidebarMenuButton>
              {item.popular ? (
                <SidebarMenuBadge className="bg-sky-500/15 text-sky-600 dark:text-sky-400">Popular</SidebarMenuBadge>
              ) : item.badge != null && item.badge !== 0 ? (
                <SidebarMenuBadge>{item.badge}</SidebarMenuBadge>
              ) : null}
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}
