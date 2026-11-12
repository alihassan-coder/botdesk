import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { NewGroupDialog } from "./new-group-dialog";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

beforeEach(() => push.mockClear());
afterEach(() => vi.restoreAllMocks());

describe("NewGroupDialog", () => {
  it("creates a group with the bots and people you tick, then opens it", async () => {
    const onOpenChange = vi.fn();
    const { user } = renderUI(<NewGroupDialog open onOpenChange={onOpenChange} />);

    await user.type(screen.getByLabelText("Name"), "Hiring");
    await user.click(screen.getByRole("checkbox", { name: /Talent Scout/ }));
    await user.click(screen.getByRole("checkbox", { name: /Sara Khan/ }));
    await user.click(screen.getByRole("button", { name: "Create" }));

    const group = getStoreSnapshot().threads[0];
    expect(group).toMatchObject({ kind: "group", title: "Hiring" });
    expect(group.participants).toEqual([
      { type: "user", id: "u_me" },
      { type: "user", id: "u_sara" },
      { type: "bot", id: "b_talent" },
    ]);
    expect(push).toHaveBeenCalledWith(`/chat/${group.id}`);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("lists your teammates but not you", () => {
    renderUI(<NewGroupDialog open onOpenChange={() => {}} />);
    expect(screen.getByRole("checkbox", { name: /Omar Farooq/ })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Ali Hassan/ })).not.toBeInTheDocument();
  });

  it("waits for a name and a bot before Create works", async () => {
    const { user } = renderUI(<NewGroupDialog open onOpenChange={() => {}} />);
    const create = screen.getByRole("button", { name: "Create" });

    await user.type(screen.getByLabelText("Name"), "Ops");
    expect(create).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /Sara Khan/ }));
    expect(create).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /Chief of staff/ }));
    expect(create).toBeEnabled();
  });

  it("shows why the group wasn't created and stays open", async () => {
    vi.spyOn(actions, "createGroup").mockResolvedValue({ ok: false, error: "Some of those people or bots aren't in this organization." });
    const onOpenChange = vi.fn();
    const { user } = renderUI(<NewGroupDialog open onOpenChange={onOpenChange} />);

    await user.type(screen.getByLabelText("Name"), "Ops");
    await user.click(screen.getByRole("checkbox", { name: /Chief of staff/ }));
    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByText("Some of those people or bots aren't in this organization.")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
  });
});
