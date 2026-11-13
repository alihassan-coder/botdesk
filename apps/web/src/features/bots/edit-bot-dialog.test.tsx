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
