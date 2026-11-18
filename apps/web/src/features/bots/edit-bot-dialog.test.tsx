import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { EditBotDialog } from "./edit-bot-dialog";

const chief = () => getStoreSnapshot().bots.find((b) => b.id === "b_chief")!;

describe("EditBotDialog", () => {
  it("owners and admins can change the budget", async () => {
    const { user } = renderUI(<EditBotDialog bot={chief()} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    const budget = screen.getByLabelText("Monthly budget (USD)");
    await user.clear(budget);
    await user.type(budget, "120");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(chief().monthlyBudgetUsd).toBe(120);
  });

  it("members see the budget but can't change it", async () => {
    await actions.changeMemberRole("u_me", "member");
    const { user } = renderUI(<EditBotDialog bot={chief()} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));

    const budget = screen.getByLabelText("Monthly budget (USD)");
    expect(budget).toHaveAttribute("readonly");
    expect(budget).toHaveAccessibleDescription("Only owners and admins can change budgets.");
  });
});

describe("EditBotDialog under the organization's ceiling", () => {
  it("offers only levels up to the ceiling", async () => {
    await actions.setMaxSecurityLevel("ask-before-acting");
    const { user } = renderUI(<EditBotDialog bot={chief()} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByRole("radio", { name: /^Autonomous/ })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /^Read only/ })).toBeEnabled();
  });

  it("a bot already above a lowered ceiling shows its own level and can still be saved", async () => {
    await actions.editBot("b_chief", { securityLevel: "autonomous" });
    await actions.setMaxSecurityLevel("read-only");
    const { user } = renderUI(<EditBotDialog bot={chief()} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByRole("radio", { name: /^Autonomous/ })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(chief().securityLevel).toBe("autonomous");
  });
});
