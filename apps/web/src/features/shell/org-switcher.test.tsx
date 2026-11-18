import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderUI } from "@/test/render";
import { OrgSwitcher } from "./org-switcher";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("OrgSwitcher", () => {
  it("New organization opens the create dialog", async () => {
    const { user } = renderUI(<OrgSwitcher />);

    await user.click(screen.getByRole("button", { name: "Organization: Acme Labs" }));
    await user.click(await screen.findByRole("menuitem", { name: "New organization" }));

    const dialog = await screen.findByRole("dialog", { name: "New organization" });
    expect(dialog).toHaveTextContent("You'll be its owner.");
    expect(screen.getByLabelText("Name")).toHaveValue("");
  });
});
