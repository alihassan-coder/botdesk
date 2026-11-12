import { expect, test } from "./fixtures";

/* Phone (Pixel 7 size): one screen at a time. */

test("home is the list of your bots", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("link", { name: /Inbox Manager/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Approvals, 3 waiting/ })).toBeVisible();
});

test("tapping a bot opens its chat, and back returns to the list", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /Inbox Manager/ }).click();
  await expect(page).toHaveURL(/\/chat\/t_inbox$/);
  await expect(page.getByRole("textbox", { name: "Message Inbox Manager" })).toBeVisible();

  await page.getByRole("link", { name: "Back to bots" }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("details open as a sheet from the bottom", async ({ page }) => {
  await page.goto("/chat/t_bugs");
  await page.getByRole("button", { name: "Details" }).click();
  const sheet = page.getByRole("dialog", { name: "Details for Bug Fixer" });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText("Autonomous within limits")).toBeVisible();
});

test("the menu opens every page and the theme switch", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Menu" }).click();
  await expect(page.getByRole("link", { name: "Settings" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Marketplace" })).toBeVisible();
});
