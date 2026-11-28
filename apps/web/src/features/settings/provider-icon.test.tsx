import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ModelProviderKind } from "@/data/types";
import { ProviderIcon } from "./provider-icon";

const logoOf = (kind: ModelProviderKind) => render(<ProviderIcon kind={kind} />).container.firstElementChild!;

describe("ProviderIcon", () => {
  it.each<ModelProviderKind>(["anthropic", "openai", "gemini", "openrouter", "groq"])(
    "draws %s's own logo",
    (kind) => {
      const logo = logoOf(kind);
      expect(logo).toHaveAttribute("data-logo", "brand");
      expect(logo.querySelector("path")?.getAttribute("d")).toBeTruthy();
    },
  );

  it("gives a custom server a neutral icon, since it can be any server", () => {
    expect(logoOf("custom")).toHaveAttribute("data-logo", "fallback");
  });

  it("is hidden from screen readers: the provider's name is written next to it", () => {
    expect(logoOf("openai")).toHaveAttribute("aria-hidden");
  });
});
