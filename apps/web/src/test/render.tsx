import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Renders a component the way the app does (inside the providers it expects:
 * tooltips, and the sidebar context that page headers use) and returns a `user`
 * for clicking and typing like a real person.
 */
export function renderUI(ui: React.ReactElement) {
  return {
    user: userEvent.setup(),
    ...render(
      <TooltipProvider>
        <SidebarProvider>{ui}</SidebarProvider>
      </TooltipProvider>,
    ),
  };
}
