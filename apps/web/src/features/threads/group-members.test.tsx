import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { GroupMembers } from "./group-members";

const launch = () => getStoreSnapshot().threads.find((t) => t.id === "t_launch")!;

describe("GroupMembers", () => {
  it("its creator renames the group", async () => {
    const { user, rerender } = renderUI(<GroupMembers thread={launch()} />);
    await user.click(screen.getByRole("button", { name: "Rename group" }));
    const name = screen.getByRole("textbox", { name: "Name" });
    expect(name).toHaveValue("Launch crew");
    await user.clear(name);
    await user.type(name, "Launch week");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(launch().title).toBe("Launch week");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    rerender(<GroupMembers thread={launch()} />);
    expect(screen.getByRole("heading", { name: "Launch week" })).toBeInTheDocument();
  });

  it("adds people and bots who aren't in it yet", async () => {
    const { user, rerender } = renderUI(<GroupMembers thread={launch()} />);
    await user.click(screen.getByRole("button", { name: "Add people or bots" }));
    const dialog = screen.getByRole("dialog");
    // Chief is in the group already, so it isn't offered.
    expect(within(dialog).queryByRole("checkbox", { name: /Chief/ })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Add" })).toBeDisabled();
    await user.click(within(dialog).getByRole("checkbox", { name: /Omar Farooq/ }));
    await user.click(within(dialog).getByRole("checkbox", { name: /Inbox Manager/ }));
    await user.click(within(dialog).getByRole("button", { name: "Add" }));

    expect(launch().participants).toEqual(expect.arrayContaining([{ type: "user", id: "u_omar" }, { type: "bot", id: "b_inbox" }]));
    rerender(<GroupMembers thread={launch()} />);
    expect(screen.getByText("Omar Farooq")).toBeInTheDocument();
  });

  it("removes a bot; removing the lead leaves the group without one", async () => {
    const { user } = renderUI(<GroupMembers thread={launch()} />);
    await user.click(screen.getByRole("button", { name: "Remove Chief from the group" }));
    expect(launch().participants).not.toContainEqual({ type: "bot", id: "b_chief" });
    expect(launch().leadBotId).toBeUndefined();
  });

  it("the last person in a group has no Remove", async () => {
    await actions.removeFromGroup("t_launch", { type: "user", id: "u_sara" });
    renderUI(<GroupMembers thread={launch()} />);
    expect(screen.queryByRole("button", { name: "Remove Ali Hassan from the group" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Chief from the group" })).toBeInTheDocument();
  });

  it("a member who didn't make the group sees who's in it, without the controls", async () => {
    await expect(actions.changeMemberRole("u_me", "member")).resolves.toEqual({ ok: true });
    renderUI(<GroupMembers thread={{ ...launch(), createdBy: "u_sara" }} />);
    expect(screen.getByText("Sara Khan")).toBeInTheDocument();
    for (const name of ["Rename group", "Add people or bots", "Remove Chief from the group"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });
});
