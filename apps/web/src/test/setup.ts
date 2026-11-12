// Types for toBeInTheDocument(), toHaveValue()…
import "@testing-library/jest-dom/vitest";
import * as domMatchers from "@testing-library/jest-dom/matchers";
import { cleanup } from "@testing-library/react";
import { afterEach, expect, vi } from "vitest";
import { actions } from "@/data/store";

// Register the matchers on *our* expect. With pnpm, jest-dom's own helper can find a
// different copy of vitest and register them there, where our tests never see them.
expect.extend(domMatchers);

/*
 * Runs before every test file.
 * jsdom has no layout engine, so the browser APIs our UI asks about are stubbed here.
 */

// Screen-size checks (useIsMobile, the "/" redirect): pretend to be a desktop.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: query.includes("min-width"),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Used by Radix popovers and the message scroller.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
Element.prototype.scrollIntoView ??= vi.fn();
// Radix Select asks about pointer capture when it opens.
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.setPointerCapture ??= vi.fn();
Element.prototype.releasePointerCapture ??= vi.fn();

// Each test starts with fresh mock data, an empty page and nothing saved (no session, no preferences).
afterEach(() => {
  cleanup();
  actions.reset();
  localStorage.clear();
  vi.useRealTimers();
});
