import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { GroupLead } from "./group-lead";

const launch = () => getStoreSnapshot().threads.find((t) => t.id === "t_launch")!;

describe("GroupLead", () => {
  it("its creator picks another of the group's bots, or none", async () => {
    const { user, rerender } = renderUI(<GroupLead thread={launch()} />);
    const select = screen.getByRole("combobox", { name: "Lead" });
    expect(select).toHaveValue("b_chief");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Chief", "Sales Outbound", "Bug Fixer", "No lead"]);

    await user.selectOptions(select, "Bug Fixer");
    expect(launch().leadBotId).toBe("b_bugs");
    rerender(<GroupLead thread={launch()} />);
    expect(screen.getByText("Bug Fixer answers messages that don't @mention a bot.")).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: "Lead" }), "No lead");
    expect(launch().leadBotId).toBeUndefined();
  });

  it("a member who didn't make the group just sees who leads", async () => {
    await expect(actions.changeMemberRole("u_me", "member")).resolves.toEqual({ ok: true });
    renderUI(<GroupLead thread={{ ...launch(), createdBy: "u_sara" }} />);

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByText("Chief")).toBeInTheDocument();
  });
});
