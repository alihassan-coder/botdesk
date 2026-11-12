import { expect, test } from "@playwright/test";

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
    await expect(page.getByText("Hi! I'm Researcher.")).toBeVisible();
    await expect(page.locator("[data-sidebar=sidebar]").getByRole("link", { name: /Researcher/ })).toBeVisible();
  });
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
});
