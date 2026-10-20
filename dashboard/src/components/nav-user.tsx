"use client";

import { LogOutIcon } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { logout } from "@/app/actions/auth";

export function NavUser({
  user,
}: {
  user: { name: string; email: string; image?: string | null };
}) {
  const initials = user.name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase() || "U";
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton size="lg" className="cursor-default">
          <Avatar className="size-8 rounded-lg">
            {user.image ? <AvatarImage src={user.image} alt="" /> : null}
            <AvatarFallback className="rounded-lg">{initials}</AvatarFallback>
          </Avatar>
          <div className="grid flex-1 text-left text-sm leading-tight">
            <span className="truncate font-medium">{user.name}</span>
            <span className="truncate text-xs text-foreground/70">{user.email}</span>
          </div>
        </SidebarMenuButton>
      </SidebarMenuItem>
      <SidebarMenuItem>
        <form action={logout}>
          <SidebarMenuButton
            type="submit"
            className="bg-muted/50 font-medium text-foreground hover:bg-muted"
          >
            <LogOutIcon />
            <span>Sign out</span>
          </SidebarMenuButton>
        </form>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
