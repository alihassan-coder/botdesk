import type { BrowserKey } from "@/data/types";

/*
 * Taking over a bot's browser (ADR 0017 §5): turning what a person does to the live picture into
 * what the API's `POST …/browser/input` takes. Pure, so it's tested without a browser.
 */

/** The special keys the API takes, besides text. Space is sent as text (" "). */
const SPECIAL_KEYS = new Set<string>([
  "Enter", "Tab", "Backspace", "Delete", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown",
]);

/** The API takes at most this much text in one `type`. */
export const MAX_TYPED = 500;

interface Box { left: number; top: number; width: number; height: number }

/**
 * Where a click on the picture lands on the page. The picture is the page scaled to fit, so the
 * point is scaled back up to page pixels and kept inside the page (the API takes 0..width-1).
 */
export function toPagePoint(clientX: number, clientY: number, shown: Box, page: { width: number; height: number }) {
  const scale = (offset: number, size: number, pageSize: number) =>
    Math.min(pageSize - 1, Math.max(0, Math.floor((offset / size) * pageSize)));
  return { x: scale(clientX - shown.left, shown.width, page.width), y: scale(clientY - shown.top, shown.height, page.height) };
}

/** What a key press means in the bot's browser: text to type, a key for the page, or nothing (it stays this browser's). */
export type KeyMeaning = { kind: "text"; text: string } | { kind: "key"; key: BrowserKey } | null;

export function keyMeaning(e: { key: string; shiftKey: boolean; ctrlKey: boolean; metaKey: boolean; altKey: boolean }): KeyMeaning {
  // Shortcuts (copy, paste, reload…) stay with this browser; a paste arrives as text on its own.
  // Ctrl with Alt is AltGr on Windows keyboards, which types characters like @ and €.
  if (e.metaKey || (e.ctrlKey && !e.altKey)) return null;
  if (e.key === "Tab") return { kind: "key", key: e.shiftKey ? "Shift+Tab" : "Tab" };
  if (SPECIAL_KEYS.has(e.key)) return { kind: "key", key: e.key as BrowserKey };
  if ([...e.key].length === 1) return { kind: "text", text: e.key };
  return null; // Shift on its own, F-keys, dead keys…
}

/** A wheel turn as page pixels to scroll (lines and pages turned into pixels), within the API's ±3000. */
export function scrollDelta(deltaY: number, deltaMode: number): number {
  const px = deltaMode === 1 ? deltaY * 40 : deltaMode === 2 ? deltaY * 800 : deltaY;
  return Math.max(-3000, Math.min(3000, Math.round(px)));
}

/** Text in pieces the API takes, never splitting a character (an emoji is two UTF-16 units). */
export function textPieces(text: string, size = MAX_TYPED): string[] {
  const chars = [...text];
  const pieces: string[] = [];
  for (let i = 0; i < chars.length; i += size) pieces.push(chars.slice(i, i + size).join(""));
  return pieces;
}

/** What someone typed in the address field, as an address: "example.com" → "https://example.com". */
export function toAddress(typed: string): string {
  const text = typed.trim();
  if (!text) return "";
  return /^[a-z][a-z\d+.-]*:\/\//i.test(text) ? text : `https://${text}`;
}
