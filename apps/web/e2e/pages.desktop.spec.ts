import { expect, test } from "./fixtures";

/* Desktop: the app pages (marketplace, new bot, approvals, routines, apps, settings). */

test.describe("Marketplace", () => {
  test("filters by category", async ({ page }) => {
    await page.goto("/marketplace");
    await page.getByRole("button", { name: "Finance" }).click();
    await expect(page.getByRole("heading", { name: "Expense Clerk" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Researcher" })).toHaveCount(0);
  });

  test("hiring a bot opens its chat, where it says hello", async ({ page }) => {
    await page.goto("/marketplace");
    await page.getByRole("button", { name: "Hire Researcher" }).click();
    await expect(page).toHaveURL(/\/chat\/t_/);
    await expect(page.getByLabel("Conversation with Researcher").getByText("Hi! I'm Researcher.")).toBeVisible();
    await expect(page.locator("[data-sidebar=sidebar]").getByRole("link", { name: /Researcher/ })).toBeVisible();
  });
});

test("editing a bot from its details, then removing it", async ({ page }) => {
  await page.goto("/chat/t_talent");
  const details = page.getByRole("complementary", { name: "Details" });
  await details.getByRole("button", { name: "Edit" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill("Talent Finder");
  await dialog.getByRole("button", { name: "Save changes" }).click();
  await expect(details.getByRole("heading", { name: "Talent Finder" })).toBeVisible();

  await details.getByRole("button", { name: "Remove" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Remove" }).click();
  await expect(page).not.toHaveURL(/t_talent/);
  await expect(page.locator("[data-sidebar=sidebar]").getByRole("link", { name: /Talent/ })).toHaveCount(0);
});

test("creating a bot from scratch", async ({ page }) => {
  await page.goto("/bots/new");
  await page.getByLabel("Name").fill("Release Notes");
  await page.getByLabel("Role").fill("Writing");
  await page.getByLabel("What it does").fill("Turns merged pull requests into release notes.");
  await expect(page.getByText("Writing · @release-notes")).toBeVisible();

  await page.getByRole("button", { name: "Create bot" }).click();
  await expect(page).toHaveURL(/\/chat\/t_/);
  // The greeting is also the sidebar preview, so look inside the conversation itself.
  await expect(page.getByLabel("Conversation with Release Notes").getByText("Hi! I'm Release Notes. Turns merged pull requests into release notes.")).toBeVisible();
});

test("the approvals inbox collects every request", async ({ page }) => {
  await page.goto("/approvals");
  await expect(page.getByRole("tab", { name: "Waiting · 3" })).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).first().click();
  await expect(page.getByRole("tab", { name: "Waiting · 2" })).toBeVisible();

  await page.getByRole("tab", { name: /Decided/ }).click();
  await expect(page.getByText(/Approved by you/).first()).toBeVisible();
});

test("routines can be switched off", async ({ page }) => {
  await page.goto("/routines");
  const toggle = page.getByRole("switch", { name: "Run Morning triage" });
  await expect(toggle).toBeChecked();
  await toggle.click();
  await expect(toggle).not.toBeChecked();
});

test("connecting a custom MCP server", async ({ page }) => {
  await page.goto("/apps");
  await page.getByRole("button", { name: "Connect Custom MCP server" }).click();
  await page.getByLabel("Server URL").fill("https://mcp.acme.dev/sse");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByRole("region", { name: "Connected" })).toContainText("https://mcp.acme.dev/sse");
});

test.describe("Settings", () => {
  test("opens on Profile and every section is one click away", async ({ page }) => {
    await page.goto("/settings");
    await expect(page).toHaveURL(/\/settings\/profile$/);
    for (const [link, heading] of [
      ["Organization", "Delete organization"],
      ["Appearance", "Theme"],
      ["Models & keys", "Models"],
      ["Security", "What each level allows"],
      ["Members", "Members"],
      ["Usage & budgets", "Budgets"],
      ["Memory", "Memory"],
    ]) {
      await page.getByRole("navigation", { name: "Settings sections" }).getByRole("link", { name: link }).click();
      await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
    }
  });

  test("an added API key is only ever shown masked", async ({ page }) => {
    await page.goto("/settings/models");
    await page.getByRole("button", { name: "Add key" }).click();
    await page.getByLabel("API key", { exact: true }).fill("sk-test-1234567890abcd");
    await page.getByRole("dialog").getByRole("button", { name: "Add key" }).click();
    await expect(page.getByText("sk-t…abcd")).toBeVisible();
    await expect(page.getByText("sk-test-1234567890abcd")).toHaveCount(0);
  });

  test("inviting a member", async ({ page }) => {
    await page.goto("/settings/members");
    await page.getByRole("button", { name: "Invite" }).click();
    await page.getByLabel("Email").fill("zara.ahmed@acme.dev");
    await page.getByRole("button", { name: "Send invite" }).click();
    await expect(page.getByText("Zara Ahmed")).toBeVisible();
  });

  test("changing the accent colour repaints the app", async ({ page }) => {
    await page.goto("/settings/appearance");
    await page.getByRole("radio", { name: "Teal" }).click();
    const brand = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--brand").trim());
    expect(brand).toBe("#0f8f7a");
  });

  test("the theme and accent pickers work with the keyboard", async ({ page }) => {
    // Radix selects a radio when focus lands while the arrow key is still down (it moves focus
    // a tick later). A person's key press lasts that long; Playwright's press() doesn't, so hold it.
    const arrowRight = async () => {
      await page.keyboard.down("ArrowRight");
      await page.waitForTimeout(50);
      await page.keyboard.up("ArrowRight");
    };
    await page.goto("/settings/appearance");
    await page.getByRole("radio", { name: "Light" }).click();
    await expect(page.getByRole("radio", { name: "Light" })).toBeChecked();
    await arrowRight();
    await expect(page.getByRole("radio", { name: "Dark" })).toBeFocused();
    await expect(page.getByRole("radio", { name: "Dark" })).toBeChecked();
    await expect(page.locator("html")).toHaveClass(/dark/);

    // One Tab stop per group: Tab goes from the theme to the selected accent, then to the custom colour.
    await page.keyboard.press("Tab");
    await expect(page.getByRole("radio", { name: "Ultramarine" })).toBeFocused();
    await arrowRight();
    await expect(page.getByRole("radio", { name: "Teal" })).toBeChecked();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Custom colour")).toBeFocused();
  });

  test("a custom accent colour, with readable text on it", async ({ page }) => {
    await page.goto("/settings/appearance");
    await page.getByLabel("Custom colour").fill("#ffd60a");
    await expect(page.getByText("#FFD60A")).toBeVisible();
    const [brand, text] = await page.evaluate(() => {
      const s = getComputedStyle(document.documentElement);
      return [s.getPropertyValue("--brand").trim(), s.getPropertyValue("--brand-foreground").trim()];
    });
    expect(brand).toBe("#ffd60a");
    expect(text).toBe("#000000"); // yellow is light, so text on it turns black
  });

  test("the Settings link opens Profile, and the section links stay in view while scrolling", async ({ page }) => {
    await page.goto("/chat/t_chief");
    await page.locator("[data-sidebar=sidebar]").getByRole("link", { name: "Settings" }).click();
    await expect(page).toHaveURL(/\/settings\/profile$/);

    await page.goto("/settings/security");
    const nav = page.getByRole("navigation", { name: "Settings sections" });
    await page.getByRole("heading", { name: "What each level allows" }).scrollIntoViewIfNeeded();
    await expect(nav).toBeInViewport();
  });

  test("renaming the organization updates the sidebar", async ({ page }) => {
    await page.goto("/settings/organization");
    await page.getByLabel("Name").fill("Acme Inc");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("button", { name: "Organization: Acme Inc" })).toBeVisible();
  });

  test("the organization address can be typed with dashes", async ({ page }) => {
    await page.goto("/settings/organization");
    const address = page.getByLabel("Address");
    await address.clear();
    await address.pressSequentially("my team-");
    await expect(address).toHaveValue("my-team-");
    await expect(page.getByText("botdesk.app/my-team.")).toBeVisible();
  });
});

test("the organization menu leads to managing the org", async ({ page }) => {
  await page.goto("/chat/t_chief");
  await page.getByRole("button", { name: "Organization: Acme Labs" }).click();
  await page.getByRole("menuitem", { name: "Manage organization" }).click();
  await expect(page).toHaveURL(/\/settings\/organization$/);
});

test("the sidebar collapses to an icon rail and stays that way", async ({ page }) => {
  await page.goto("/chat/t_chief");
  const sidebar = page.locator("[data-slot=sidebar][data-state]");
  await expect(sidebar).toHaveAttribute("data-state", "expanded");

  // The header button (the rail on the sidebar's edge toggles too).
  await page.locator("[data-sidebar=sidebar] [data-sidebar=trigger]").click();
  await expect(sidebar).toHaveAttribute("data-state", "collapsed");
  await expect(page.locator("[data-sidebar=sidebar]").getByText("Coordinating 3 handoffs")).toBeHidden();

  await page.reload();
  await expect(sidebar).toHaveAttribute("data-state", "collapsed");

  // Collapsed, the logo is the expand button.
  await page.getByRole("button", { name: "Expand sidebar" }).click();
  await expect(sidebar).toHaveAttribute("data-state", "expanded");
});

test("creating a routine; its bot confirms in chat", async ({ page }) => {
  await page.goto("/routines");
  await page.getByRole("link", { name: "New routine" }).click();
  await page.getByLabel("Name").fill("Friday expense report");
  await page.getByLabel("How often").click();
  await page.getByRole("option", { name: "Every week" }).click();
  await page.getByLabel("Day").click();
  await page.getByRole("option", { name: "Friday" }).click();
  await page.getByLabel("Time").fill("17:00");
  await expect(page.getByText("Every Friday at 5 PM")).toBeVisible();
  await page.getByLabel("Step 1", { exact: true }).fill("Search Gmail for receipts");
  await page.getByRole("button", { name: "Add step" }).click();
  await page.getByLabel("Step 2", { exact: true }).fill("File the report");
  await page.getByRole("button", { name: "Save routine" }).click();

  await expect(page).toHaveURL(/\/routines$/);
  await expect(page.getByRole("article", { name: "Friday expense report" })).toContainText("Every Friday at 5 PM");
});

test("a routine needs a name and at least one step", async ({ page }) => {
  await page.goto("/routines/new");
  await page.getByRole("button", { name: "Save routine" }).click();
  await expect(page.getByText("Give the routine a name.")).toBeVisible();
  await expect(page.getByText("Add at least one step.")).toBeVisible();
});
