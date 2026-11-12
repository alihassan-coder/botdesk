/**
 * Screenshots explore.html to explore.png (2×). Run from the repo root:
 *   node docs/design/logo/v8/render.mjs
 * Uses Playwright from apps/web and the installed Chrome.
 */
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, "../../../../apps/web/package.json"));
const { chromium } = require("@playwright/test");

const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({ deviceScaleFactor: 2, viewport: { width: 1600, height: 1200 } });
await page.goto(pathToFileURL(join(here, "explore.html")).href, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: join(here, "explore.png"), fullPage: true });
await browser.close();
console.log("✓ explore.png");
