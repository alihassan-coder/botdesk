import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Renders a component the way the app does (inside the providers it expects)
 * and returns a `user` for clicking and typing like a real person.
 */
export function renderUI(ui: React.ReactElement) {
  return {
    user: userEvent.setup(),
    ...render(<TooltipProvider>{ui}</TooltipProvider>),
  };
}
