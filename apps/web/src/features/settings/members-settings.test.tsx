import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
