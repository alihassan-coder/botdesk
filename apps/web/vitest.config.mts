import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/*
 * Unit and component tests (`pnpm test`).
 * - Logic tests sit next to the code: src/lib/*.test.ts, src/data/store.test.ts.
 * - Component tests render in jsdom (a simulated browser) with Testing Library.
 * - Real-browser tests live in e2e/ and run with Playwright (`pnpm test:e2e`), not here.
 */
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
