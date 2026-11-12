"use client";

import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { useStoredState } from "@/hooks/use-stored-state";
import { CommandPalette } from "@/features/command-palette/command-palette";
import { useApplySavedAccent } from "@/features/settings/accent";
import { AppSidebar } from "./app-sidebar";
import { AuthGate } from "./auth-gate";

/**
 * The frame around every signed-in page: the bot sidebar on the left, the page on the right.
 * The sidebar collapses to an icon rail (remembered in this browser); on phones it's a sheet.
 * Nothing renders until you're signed in (AuthGate).
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  useApplySavedAccent();
  const [sidebarOpen, setSidebarOpen] = useStoredState("botdesk.sidebar.open", true);

  return (
    <AuthGate>
      <SidebarProvider
        open={sidebarOpen}
        onOpenChange={setSidebarOpen}
        style={{ "--sidebar-width": "17.5rem", "--sidebar-width-icon": "4rem" } as React.CSSProperties}
        className="h-svh"
      >
        <AppSidebar />
        <SidebarInset className="min-w-0 overflow-hidden">{children}</SidebarInset>
        <CommandPalette />
      </SidebarProvider>
    </AuthGate>
  );
}
