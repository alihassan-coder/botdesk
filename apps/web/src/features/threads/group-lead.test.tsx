import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { GroupLead } from "./group-lead";

const launch = () => getStoreSnapshot().threads.find((t) => t.id === "t_launch")!;

describe("GroupLead", () => {
  it("its creator picks another of the group's bots, or none", async () => {
    const { user, rerender } = renderUI(<GroupLead thread={launch()} />);
    const lead = screen.getByRole("combobox", { name: "Lead" });
    expect(lead).toHaveTextContent("Chief");

    await user.click(lead);
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["No lead", "Chief", "Sales Outbound", "Bug Fixer"]);
    await user.click(screen.getByRole("option", { name: "Bug Fixer" }));
    await waitFor(() => expect(launch().leadBotId).toBe("b_bugs"));
    rerender(<GroupLead thread={launch()} />);
    expect(screen.getByText("Bug Fixer answers messages that don't @mention a bot.")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Lead" }));
    await user.click(screen.getByRole("option", { name: "No lead" }));
    await waitFor(() => expect(launch().leadBotId).toBeUndefined());
    rerender(<GroupLead thread={launch()} />);
    expect(screen.getByRole("combobox", { name: "Lead" })).toHaveTextContent("No lead");
    expect(screen.getByText("Only the bots you @mention reply.")).toBeInTheDocument();
  });

  it("works from the keyboard", async () => {
    const { user } = renderUI(<GroupLead thread={launch()} />);
    screen.getByRole("combobox", { name: "Lead" }).focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
    // The list opens on the current lead (Chief); one down is Sales Outbound.
    await user.keyboard("{ArrowDown}{Enter}");
    await waitFor(() => expect(launch().leadBotId).toBe("b_sales"));
  });

  it("a member who didn't make the group just sees who leads", async () => {
    await expect(actions.changeMemberRole("u_me", "member")).resolves.toEqual({ ok: true });
    renderUI(<GroupLead thread={{ ...launch(), createdBy: "u_sara" }} />);

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByText("Chief")).toBeInTheDocument();
  });
});
