import { screen } from "@testing-library/react";
import { ThemeProvider } from "next-themes";
import { describe, expect, it } from "vitest";
import { renderUI } from "@/test/render";
import { AppearanceSettings } from "./appearance-settings";

function renderAppearance() {
  return renderUI(
    <ThemeProvider attribute="class" defaultTheme="light">
      <AppearanceSettings />
    </ThemeProvider>,
  );
}

/**
 * Radix selects a radio when focus arrives while an arrow key is still down, and it moves
 * focus on the next tick. A real key press lasts that long; user-event's is instant, so hold it.
 */
async function pressArrowRight(user: ReturnType<typeof renderUI>["user"]) {
  await user.keyboard("{ArrowRight>}");
  await new Promise((r) => setTimeout(r, 0));
  await user.keyboard("{/ArrowRight}");
}

describe("AppearanceSettings", () => {
  it("moves through themes with the arrow keys, one Tab stop for the group", async () => {
    const { user } = renderAppearance();
    expect(screen.getByRole("radio", { name: "Light" })).toBeChecked();

    await user.tab();
    expect(screen.getByRole("radio", { name: "Light" })).toHaveFocus();

    await pressArrowRight(user);
    expect(screen.getByRole("radio", { name: "Dark" })).toHaveFocus();
    expect(screen.getByRole("radio", { name: "Dark" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Light" })).not.toBeChecked();

    // Tab leaves the theme group and lands on the selected accent.
    await user.tab();
    expect(screen.getByRole("radio", { name: "Ultramarine" })).toHaveFocus();
  });

  it("moves through accents with the arrow keys, then on to the custom colour", async () => {
    const { user } = renderAppearance();
    screen.getByRole("radio", { name: "Ultramarine" }).focus();

    await pressArrowRight(user);
    expect(screen.getByRole("radio", { name: "Teal" })).toHaveFocus();
    expect(screen.getByRole("radio", { name: "Teal" })).toBeChecked();
    expect(localStorage.getItem("botdesk.accent")).toContain("teal");

    await user.tab();
    expect(screen.getByLabelText("Custom colour")).toHaveFocus();
  });
});
