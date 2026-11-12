import { expect, test } from "@playwright/test";
import { test as signedInTest } from "./fixtures";

/* Sign in, sign up, password reset and sign out. These start signed out (plain Playwright test). */

test("the app sends you to sign in, then back to the page you wanted", async ({ page }) => {
  await page.goto("/settings/members");
  await expect(page).toHaveURL(/\/sign-in\?next=%2Fsettings%2Fmembers$/);

  await page.getByLabel("Email").fill("ali@acme.dev");
  await page.getByLabel("Password", { exact: true }).fill("botdesk123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/settings\/members$/);
});

test("a wrong password says so and keeps you on the page", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill("ali@acme.dev");
  await page.getByLabel("Password", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  // Next.js keeps its own (empty) route announcer with role="alert", so match ours by text.
  await expect(page.getByRole("alert").filter({ hasText: "don't match" })).toHaveText("That email and password don't match.");
  await expect(page).toHaveURL(/\/sign-in/);
});

test("the password can be shown while typing", async ({ page }) => {
  await page.goto("/sign-in");
  const password = page.getByLabel("Password", { exact: true });
  await password.fill("botdesk123");
  await expect(password).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(password).toHaveAttribute("type", "text");
});

test("creating an account signs you in", async ({ page }) => {
  await page.goto("/sign-up");
  await page.getByLabel("Your name").fill("Zara Ahmed");
  await page.getByLabel("Work email").fill("zara@acme.dev");
  await page.getByLabel("Password", { exact: true }).fill("short");
  await expect(page.getByRole("button", { name: "Create account" })).toBeDisabled();
  await page.getByLabel("Password", { exact: true }).fill("long-enough-pw");
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page).toHaveURL(/\/chat\//);
  await expect(page.getByRole("button", { name: "Account: Zara Ahmed" })).toBeVisible();
});

test("signing up with an existing email points you to sign in", async ({ page }) => {
  await page.goto("/sign-up");
  await page.getByLabel("Your name").fill("Ali");
  await page.getByLabel("Work email").fill("ali@acme.dev");
  await page.getByLabel("Password", { exact: true }).fill("long-enough-pw");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "already exists" })).toBeVisible();
});

test("forgot password confirms without revealing who has an account", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByRole("link", { name: "Forgot password?" }).click();
  await page.getByLabel("Email").fill("someone@example.com");
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
  await expect(page.getByText(/If someone@example.com has an account/)).toBeVisible();
});

signedInTest("signing out returns you to sign in, and the app stays locked", async ({ page }) => {
  await page.goto("/chat/t_chief");
  // Tell the test fixture not to sign us back in on the next page load.
  await page.evaluate(() => sessionStorage.setItem("e2e.signedOut", "1"));
  await page.getByRole("button", { name: "Account: Ali Hassan" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  // You chose to leave, so signing in again shouldn't drop you back on that chat.
  await expect(page).toHaveURL(/\/sign-in$/);
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();

  await page.goto("/chat/t_chief");
  await expect(page).toHaveURL(/\/sign-in\?next=/);
});
