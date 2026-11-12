import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { actions } from "@/data/store";
import { renderUI } from "@/test/render";
import { InviteDialog } from "./invite-dialog";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("InviteDialog", () => {
  it("shows the invite link to copy when the API returns one", async () => {
    vi.spyOn(actions, "inviteMember").mockResolvedValue({ ok: true, inviteUrl: "http://localhost:3000/invite/abc" });
    const { user } = renderUI(<InviteDialog />);

    await user.click(screen.getByRole("button", { name: "Invite" }));
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.click(screen.getByRole("button", { name: "Send invite" }));

    expect(await screen.findByLabelText("Invite link")).toHaveValue("http://localhost:3000/invite/abc");
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
  });

  it("shows why an invite was refused and keeps the form open", async () => {
    vi.spyOn(actions, "inviteMember").mockResolvedValue({ ok: false, error: "Only admins can invite people." });
    const { user } = renderUI(<InviteDialog />);

    await user.click(screen.getByRole("button", { name: "Invite" }));
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.click(screen.getByRole("button", { name: "Send invite" }));

    expect(await screen.findByText("Only admins can invite people.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send invite" })).toBeInTheDocument();
  });
});
