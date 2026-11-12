import { expect, test } from "@playwright/test";

/* Desktop, 1440×900: sidebar + chat + details pane. Each test starts from fresh mock data (a page load resets it). */

test("home opens your most recent chat", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/chat\/t_chief$/);
  await expect(page.getByRole("heading", { name: "Chief", level: 1 })).toBeVisible();
});

test("sidebar lists pinned bots, bots and groups with approvals waiting", async ({ page }) => {
  await page.goto("/chat/t_chief");
  const sidebar = page.locator("[data-sidebar=sidebar]");
  await expect(sidebar.getByRole("region", { name: "Pinned" })).toContainText("Chief");
  await expect(sidebar.getByRole("region", { name: "Bots" })).toContainText("Inbox Manager");
  await expect(sidebar.getByRole("region", { name: "Groups" })).toContainText("Launch crew");
  await expect(sidebar.getByRole("link", { name: "Approvals, 3 waiting" })).toBeVisible();
});

test("searching the sidebar filters bots", async ({ page }) => {
  await page.goto("/chat/t_chief");
  await page.getByRole("textbox", { name: "Search bots and groups" }).fill("expense");
  const sidebar = page.locator("[data-sidebar=sidebar]");
  await expect(sidebar.getByRole("link", { name: /Expense Manager/ })).toBeVisible();
  await expect(sidebar.getByRole("link", { name: /Sales Outbound/ })).toHaveCount(0);
});

test("sending a message gets a streamed reply from the bot", async ({ page }) => {
  await page.goto("/chat/t_sales");
  const box = page.getByRole("textbox", { name: "Message Sales Outbound" });
  await box.fill("Pause tonight's run, please.");
  await box.press("Enter");

  await expect(page.getByText("Pause tonight's run, please.")).toBeVisible();
  await expect(page.getByText(/report back here/)).toBeVisible({ timeout: 10_000 });
  await expect(box).toHaveValue("");
});

test("approving an action updates the card and the approvals count", async ({ page }) => {
  await page.goto("/chat/t_inbox");
  await page.getByRole("button", { name: "Approve" }).first().click();

  await expect(page.getByText(/Approved by you/)).toBeVisible();
  await expect(page.getByText("Done: Send reply to Vicky (Globex).")).toBeVisible();
  await expect(page.locator("[data-sidebar=sidebar]").getByRole("link", { name: "Approvals, 2 waiting" })).toBeVisible();
});

test("editing an action before approving it", async ({ page }) => {
  await page.goto("/chat/t_inbox");
  await page.getByRole("button", { name: "Edit" }).nth(1).click();
  const body = page.getByLabel("Body");
  await body.fill("Not this quarter. Thanks!");
  await page.getByRole("button", { name: "Approve edited version" }).click();
  await expect(page.getByText(/Approved by you/)).toBeVisible();
});

test("answering a bot's question collapses it to your answer", async ({ page }) => {
  await page.goto("/chat/t_inbox");
  await page.getByRole("button", { name: "Ask me each time" }).click();
  await expect(page.getByRole("button", { name: "Yes, always" })).toHaveCount(0);
  await expect(page.getByText("Ask me each time")).toBeVisible();
});

test("group chats show who wrote each message, and members in details", async ({ page }) => {
  await page.goto("/chat/t_launch");
  await expect(page.getByText("Sara Khan").first()).toBeVisible();
  const details = page.getByRole("complementary", { name: "Details" });
  await expect(details.getByText("2 people · 3 bots")).toBeVisible();
});

test("the details pane can be closed, and stays closed after a reload", async ({ page }) => {
  await page.goto("/chat/t_chief");
  const details = page.getByRole("complementary", { name: "Details" });
  await expect(details).toBeVisible();

  await page.getByRole("button", { name: "Details" }).click();
  await expect(details).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Chief", level: 1 })).toBeVisible();
  await expect(details).toHaveCount(0);
});

test("switching to dark mode from the user menu", async ({ page }) => {
  await page.goto("/chat/t_chief");
  await page.getByRole("button", { name: /Ali Hassan/ }).click();
  await page.getByRole("menuitemradio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
});

test("⌘K opens the command palette and jumps to a bot", async ({ page }) => {
  await page.goto("/chat/t_chief");
  await expect(page.getByRole("heading", { name: "Chief", level: 1 })).toBeVisible();
  await page.keyboard.press("ControlOrMeta+k");
  await page.getByPlaceholder("Search bots, groups and pages…").fill("Bug Fixer");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/chat\/t_bugs$/);
});

test("an unknown chat says so and links home", async ({ page }) => {
  await page.goto("/chat/does-not-exist");
  await expect(page.getByRole("heading", { name: "This chat doesn't exist" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to your bots" })).toHaveAttribute("href", "/");
});
