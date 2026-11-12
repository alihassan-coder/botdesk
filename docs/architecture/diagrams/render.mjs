/**
 * Renders every *.mmd diagram in this folder to png/<name>.png (2× for sharp text).
 *
 *   node docs/architecture/diagrams/render.mjs
 *
 * Uses Playwright from apps/web and the installed Chrome; Mermaid loads from jsDelivr (pinned).
 * Edit the .mmd file, run this, commit both. GitHub also renders the Mermaid blocks in the docs.
 */
import { readdirSync, readFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, basename } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, "../../../apps/web/package.json"));
const { chromium } = require("@playwright/test");

const MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js";

// BotDesk brand: ultramarine accent, quiet greys, Geist-like system font.
const THEME = {
  theme: "base",
  themeVariables: {
    fontFamily: "Segoe UI, system-ui, sans-serif",
    fontSize: "15px",
    primaryColor: "#EEEDFF",
    primaryBorderColor: "#3B30FF",
    primaryTextColor: "#14141F",
    secondaryColor: "#F4F4F6",
    tertiaryColor: "#FFFFFF",
    lineColor: "#5B5B6B",
    clusterBkg: "#FAFAFC",
    clusterBorder: "#D4D4DE",
    actorBkg: "#EEEDFF",
    actorBorder: "#3B30FF",
    noteBkgColor: "#FFF6DB",
    noteBorderColor: "#E0B341",
    labelBoxBkgColor: "#EEEDFF",
    signalColor: "#14141F",
    sequenceNumberColor: "#FFFFFF",
  },
  flowchart: { curve: "basis", padding: 14, htmlLabels: true },
  sequence: { mirrorActors: false, messageMargin: 34 },
};

const outDir = join(here, "png");
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({ deviceScaleFactor: 2, viewport: { width: 2400, height: 1400 } });
await page.setContent(`<body style="margin:0;background:#fff"><div id="out" style="display:inline-block;padding:28px;background:#fff"></div></body>`);
await page.addScriptTag({ url: MERMAID });
await page.evaluate((theme) => window.mermaid.initialize({ startOnLoad: false, ...theme }), THEME);

const files = readdirSync(here).filter((f) => f.endsWith(".mmd")).sort();
for (const file of files) {
  const source = readFileSync(join(here, file), "utf8");
  const name = basename(file, ".mmd");
  await page.evaluate(
    async ({ id, source }) => {
      const { svg } = await window.mermaid.render(id, source);
      const out = document.getElementById("out");
      out.innerHTML = svg;
      // Draw at natural size: Mermaid otherwise shrinks wide diagrams to fit the page.
      const el = out.querySelector("svg");
      const width = el.viewBox.baseVal.width;
      el.style.maxWidth = "none";
      el.setAttribute("width", String(width));
      el.setAttribute("height", String(el.viewBox.baseVal.height));
    },
    { id: `d${name.replace(/\W/g, "")}`, source },
  );
  await page.locator("#out").screenshot({ path: join(outDir, `${name}.png`) });
  console.log(`✓ png/${name}.png`);
}

await browser.close();
