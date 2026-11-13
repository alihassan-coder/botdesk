import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { actions } from "@/data/store";
import { renderUI } from "@/test/render";
import { UsageSettings } from "./usage-settings";

const rowOf = (name: string) => screen.getByRole("link", { name }).closest("li")!;

describe("UsageSettings", () => {
  it("shows what was spent this month and each bot against its budget, the closest to its limit first", () => {
    renderUI(<UsageSettings />);
    expect(screen.getByText("Spent this month").nextSibling).toHaveTextContent("$115.60");
    expect(screen.getByText("No limit", { selector: "p" })).toBeInTheDocument(); // the org has no budget yet
    const names = within(screen.getAllByRole("list").at(-1)!).getAllByRole("link").map((a) => a.textContent);
    expect(names[0]).toBe("Sales Outbound"); // $44.20 of $60
    expect(within(rowOf("Sales Outbound")).getByText("$44.20 / $60.00")).toBeInTheDocument();
  });

  it("warns near the limit, flags a reached one, and shows no bar for a bot without a limit", async () => {
    await actions.editBot("b_sales", { monthlyBudgetUsd: 50 }); // 88% used
    await actions.editBot("b_chief", { monthlyBudgetUsd: 30 }); // past it
    await actions.editBot("b_bugs", { monthlyBudgetUsd: 0 });
    renderUI(<UsageSettings />);

    expect(within(rowOf("Sales Outbound")).getByRole("img", { name: "Close to its budget" })).toBeInTheDocument();
    expect(within(rowOf("Chief")).getByRole("img", { name: "Reached its budget" })).toBeInTheDocument();
    const bugs = rowOf("Bug Fixer");
    expect(within(bugs).getByText("No limit")).toBeInTheDocument();
    expect(within(bugs).queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("owners set the organization's budget", async () => {
    const { user } = renderUI(<UsageSettings />);
    await user.click(screen.getByRole("button", { name: "Set" }));
    await user.type(screen.getByLabelText("Organization budget per month, in US dollars"), "250");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("$250.00")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Organization budget used" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change" })).toBeInTheDocument();
  });

  it("members see the budget but can't change it", async () => {
    await actions.changeMemberRole("u_me", "member");
    renderUI(<UsageSettings />);
    expect(screen.queryByRole("button", { name: "Set" })).not.toBeInTheDocument();
  });
});
