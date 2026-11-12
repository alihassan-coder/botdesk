/**
 * Small, pure formatting helpers. No React, no dates read from the clock:
 * callers pass `now` in, so these are easy to test and give the same result
 * on the server and in the browser.
 */

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** Short "how long ago" label for lists: "now", "5m", "3h", "Yesterday", "Mon", "Nov 4". */
export function formatShortAgo(iso: string, now: number): string {
  const then = new Date(iso).getTime();
  const diff = Math.max(0, now - then);

  if (diff < MINUTE) return "now";
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h`;
  if (diff < 2 * DAY) return "Yesterday";
  if (diff < 7 * DAY) return new Date(then).toLocaleDateString("en-US", { weekday: "short" });
  return new Date(then).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Clock time for a message, e.g. "9:41 AM". */
export function formatClockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

/** Human file size: "980 B", "18 KB", "1.4 MB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Money in US dollars: "$31.40". */
export function formatUsd(amount: number): string {
  return amount.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/** The letter shown in a letter avatar: first letter of the first word. */
export function initialOf(name: string): string {
  return name.trim().charAt(0).toUpperCase() || "?";
}
