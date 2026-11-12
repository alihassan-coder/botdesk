import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { MembersSettings } from "./members-settings";

describe("MembersSettings invite", () => {
  it("won't invite someone who is already in the organization", async () => {
    const { user } = renderUI(<MembersSettings />);
    await user.click(screen.getByRole("button", { name: "Invite" }));
    await user.type(screen.getByLabelText("Email"), "Sara@acme.dev");

    expect(screen.getByText("sara@acme.dev is already in this organization.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send invite" })).toBeDisabled();
  });
});

describe("MembersSettings roles", () => {
  it("lets an owner make someone an owner, after confirming", async () => {
    const { user } = renderUI(<MembersSettings />);
    await user.click(screen.getByRole("combobox", { name: "Role for Sara Khan" }));
    await user.click(screen.getByRole("option", { name: "Owner" }));

    // Nothing changes until you confirm.
    expect(getStoreSnapshot().users.find((u) => u.name === "Sara Khan")?.role).toBe("admin");
    await user.click(screen.getByRole("button", { name: "Make owner" }));
    await waitFor(() => expect(getStoreSnapshot().users.find((u) => u.name === "Sara Khan")?.role).toBe("owner"));
  });

  it("cancelling the confirm keeps their role", async () => {
    const { user } = renderUI(<MembersSettings />);
    await user.click(screen.getByRole("combobox", { name: "Role for Omar Farooq" }));
    await user.click(screen.getByRole("option", { name: "Owner" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(getStoreSnapshot().users.find((u) => u.name === "Omar Farooq")?.role).toBe("member");
  });

  it("admins can't give or touch the owner role", async () => {
    await actions.signIn("sara@acme.dev", "botdesk123");
    const { user } = renderUI(<MembersSettings />);
    expect(screen.queryByRole("combobox", { name: "Role for Ali Hassan" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Role for Omar Farooq" }));
    expect(screen.queryByRole("option", { name: "Owner" })).not.toBeInTheDocument();
  });
});
