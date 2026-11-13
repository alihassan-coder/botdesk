import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { actions } from "@/data/store";
import { renderUI } from "@/test/render";
import { ModelsSettings } from "./models-settings";

describe("ModelsSettings", () => {
  it("shows every provider, connected ones by their last 4 characters, and the models grouped by provider", async () => {
    renderUI(<ModelsSettings />);
    const anthropic = screen.getByText("Anthropic", { selector: "p" }).closest("li")!;
    expect(within(anthropic).getByText(/••••4f2a/)).toBeInTheDocument();
    expect(within(anthropic).getByRole("button", { name: "Replace" })).toBeInTheDocument();
    const groq = screen.getByText("Groq", { selector: "p" }).closest("li")!;
    expect(within(groq).getByRole("button", { name: "Add key" })).toBeInTheDocument();

    const models = screen.getByRole("region", { name: "Models" });
    expect(within(models).getByRole("region", { name: "OpenRouter" })).toHaveTextContent("$3 / $15 per M tokens");
  });

  it("filters models as you search", async () => {
    const { user } = renderUI(<ModelsSettings />);
    await user.type(screen.getByLabelText("Search models"), "opus");
    const models = screen.getByRole("region", { name: "Models" });
    expect(within(models).getByText("Claude Opus 5.5")).toBeInTheDocument();
    expect(within(models).queryByText("gpt-5.5")).not.toBeInTheDocument();
  });

  it("members see what's connected but can't add, replace or remove keys", async () => {
    await actions.changeMemberRole("u_me", "member");
    renderUI(<ModelsSettings />);
    expect(screen.getByText("Owners and admins add API keys. Here's what's connected.")).toBeInTheDocument();
    for (const name of ["Add key", "Replace", "Remove", "Test", "Custom server"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });
});
