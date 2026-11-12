import { defineConfig, devices } from "@playwright/test";

/*
 * End-to-end tests (`pnpm test:e2e`): the real app in real Chrome.
 * - Uses the Chrome already installed on this machine, so there's no big browser download.
 * - Tests a production build on its own port (3200), so it never clashes with
 *   `pnpm dev:web` on 3000 and isn't slowed by dev-mode compiling. Change with E2E_PORT.
 * - Two screen sizes: desktop (three panes) and phone (one screen at a time).
 */
const PORT = Number(process.env.E2E_PORT ?? 3200);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    channel: "chrome",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      testMatch: /desktop\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], channel: "chrome", viewport: { width: 1440, height: 900 } },
    },
    {
      name: "phone",
      testMatch: /phone\.spec\.ts/,
      use: { ...devices["Pixel 7"], channel: "chrome" },
    },
  ],
  webServer: {
    command: `pnpm build && pnpm start --port ${PORT}`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
