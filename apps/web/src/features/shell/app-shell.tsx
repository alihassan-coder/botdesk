"use client";

import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "./app-sidebar";

/**
 * The frame around every signed-in page: the bot sidebar on the left, the page on the right.
 * On phones the sidebar becomes a sheet (and the home page shows the list itself).
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider style={{ "--sidebar-width": "17.5rem" } as React.CSSProperties} className="h-svh">
      <AppSidebar />
      <SidebarInset className="min-w-0 overflow-hidden">{children}</SidebarInset>
    </SidebarProvider>
  );
}
