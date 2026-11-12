import { test as base, expect } from "@playwright/test";

/*
 * Most tests start signed in as the demo owner (Ali), the way you'd be after signing in once.
 * The session is saved in the browser before any page loads. Auth tests (auth.desktop.spec.ts)
 * use Playwright's plain `test` instead, so they start signed out.
 */
const ALI = { id: "u_me", name: "Ali Hassan", email: "ali@acme.dev", handle: "ali", role: "owner", presence: "online" };

export const test = base.extend({
  page: async ({ page }, provide) => {
    await page.addInitScript((user) => {
      if (!sessionStorage.getItem("e2e.signedOut")) localStorage.setItem("botdesk.session", JSON.stringify({ user }));
    }, ALI);
    await provide(page);
  },
});

export { expect };
