import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderUI } from "@/test/render";
import { ProfileSettings } from "./profile-settings";

describe("ProfileSettings", () => {
  it("won't save a handle a bot or teammate already has", async () => {
    const { user } = renderUI(<ProfileSettings />);
    const handle = screen.getByLabelText("Handle");

    await user.clear(handle);
    await user.type(handle, "chief");
    expect(screen.getByText(/@chief is already someone else's/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();

    await user.clear(handle);
    await user.type(handle, "ali-h");
    expect(screen.queryByText(/already someone else's/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
  });
});
