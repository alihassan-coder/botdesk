import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { actions } from "@/data/store";
import { renderUI } from "@/test/render";
import { ModelPicker } from "./model-picker";

describe("ModelPicker", () => {
  it("lists the connected providers' models in groups, searchable, and picks one", async () => {
    const onChange = vi.fn();
    const { user } = renderUI(<ModelPicker id="m" value="" onChange={onChange} />);
    await user.click(screen.getByRole("combobox"));
    expect(screen.getByRole("group", { name: "Anthropic" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "OpenRouter" })).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Search models"), "grok");
    expect(screen.queryByRole("option", { name: /Claude Opus/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: /Grok 4.5/ }));
    expect(onChange).toHaveBeenCalledWith("openrouter:x-ai/grok-4.5");
  });

  it("points to Models & keys when no provider is connected", async () => {
    for (const id of ["anthropic", "openai", "gemini", "openrouter", "custom-gpu-box"]) await actions.removeProviderKey(id);
    renderUI(<ModelPicker id="m" value="" onChange={() => {}} />);
    expect(screen.getByRole("link", { name: "Add a key in Models & keys" })).toHaveAttribute("href", "/settings/models");
  });
});
