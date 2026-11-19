import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { GroupMembers } from "./group-members";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, back: vi.fn(), replace: vi.fn() }) }));

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

  it("removes a person only once you confirm", async () => {
    const { user } = renderUI(<GroupMembers thread={launch()} />);
    await user.click(screen.getByRole("button", { name: "Remove Sara Khan from the group" }));
    const confirm = screen.getByRole("alertdialog", { name: "Remove Sara Khan from Launch crew?" });
    expect(confirm).toHaveTextContent("They lose access to this chat.");
    await user.click(within(confirm).getByRole("button", { name: "Cancel" }));
    expect(launch().participants).toContainEqual({ type: "user", id: "u_sara" });

    await user.click(screen.getByRole("button", { name: "Remove Sara Khan from the group" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Remove" }));
    expect(launch().participants).not.toContainEqual({ type: "user", id: "u_sara" });
  });

  it("removes a bot once you confirm; removing the lead leaves the group without one", async () => {
    const { user } = renderUI(<GroupMembers thread={launch()} />);
    await user.click(screen.getByRole("button", { name: "Remove Chief from the group" }));
    const confirm = screen.getByRole("alertdialog", { name: "Remove Chief from Launch crew?" });
    await user.click(within(confirm).getByRole("button", { name: "Remove" }));
    expect(launch().participants).not.toContainEqual({ type: "bot", id: "b_chief" });
    expect(launch().leadBotId).toBeUndefined();
  });

  it("you have no Remove on yourself: you leave instead", () => {
    renderUI(<GroupMembers thread={launch()} />);
    expect(screen.queryByRole("button", { name: "Remove Ali Hassan from the group" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Sara Khan from the group" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Leave group" })).toBeInTheDocument();
  });

  it("a member who didn't make the group sees who's in it, without the controls, and may leave it", async () => {
    push.mockClear();
    await expect(actions.changeMemberRole("u_me", "member")).resolves.toEqual({ ok: true });
    const { user } = renderUI(<GroupMembers thread={{ ...launch(), createdBy: "u_sara" }} />);
    expect(screen.getByText("Sara Khan")).toBeInTheDocument();
    for (const name of ["Rename group", "Add people or bots", "Remove Chief from the group"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }

    await user.click(screen.getByRole("button", { name: "Leave group" }));
    const confirm = screen.getByRole("alertdialog", { name: "Leave Launch crew?" });
    await user.click(within(confirm).getByRole("button", { name: "Stay" }));
    expect(launch()).toBeDefined();

    await user.click(screen.getByRole("button", { name: "Leave group" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Leave" }));
    expect(getStoreSnapshot().threads.some((t) => t.id === "t_launch")).toBe(false);
    expect(push).toHaveBeenCalledWith("/");
  });

  it("leaving as the last person says the group is deleted", async () => {
    await actions.removeFromGroup("t_launch", { type: "user", id: "u_sara" });
    const { user } = renderUI(<GroupMembers thread={launch()} />);
    expect(screen.queryByRole("button", { name: "Remove Ali Hassan from the group" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Leave group" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("You're the last person in it, so it's deleted");
  });
});
