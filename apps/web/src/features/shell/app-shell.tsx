"use client";

import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { CommandPalette } from "@/features/command-palette/command-palette";
import { useApplySavedAccent } from "@/features/settings/accent";
import { AppSidebar } from "./app-sidebar";

/**
 * The frame around every signed-in page: the bot sidebar on the left, the page on the right.
 * On phones the sidebar becomes a sheet (and the home page shows the list itself).
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  useApplySavedAccent();
  return (
    <SidebarProvider style={{ "--sidebar-width": "17.5rem" } as React.CSSProperties} className="h-svh">
      <AppSidebar />
      <SidebarInset className="min-w-0 overflow-hidden">{children}</SidebarInset>
      <CommandPalette />
    </SidebarProvider>
  );
}
