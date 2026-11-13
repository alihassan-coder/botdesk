/**
 * Plain words for what an approval card shows: the tool's name, why the bot asked,
 * and how long the request stays open. Pure, so `now` is passed in.
 */

const HOUR = 3_600_000;
const DAY = 24 * HOUR;

/** "demo.send_email" → "Send email": the tool's name without its plugin. */
export function toolTitle(tool: string): string {
  const name = (tool.split(".").at(-1) ?? tool).replace(/_/g, " ");
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/**
 * The policy's trace, "level=Ask before acting · risk=external-send · tainted=no → ask",
 * as a sentence. Anything we can't read is shown as it is.
 */
export function explainReason(reason: string): string {
  const match = /level=(.+?) · risk=([\w-]+) · tainted=(yes|no) → (\w+)/.exec(reason);
  if (!match) return reason;
  const [, level, , tainted] = match;
  if (tainted === "yes") return "Asked because this run read outside content, so anything beyond internal notes needs a person.";
  return `Asked because the bot is set to “${level}”.`;
}

/** "Expires in 3 days", "Expires in 5h", "Expires in under an hour", or "Past its expiry". */
export function expiryLabel(expiresAt: string, now: number): string {
  const left = Date.parse(expiresAt) - now;
  if (left <= 0) return "Past its expiry";
  if (left < HOUR) return "Expires in under an hour";
  if (left < DAY) return `Expires in ${Math.floor(left / HOUR)}h`;
  // Rounded: a 3-day expiry asked a minute ago should still say 3 days.
  const days = Math.max(1, Math.round(left / DAY));
  return `Expires in ${days} ${days === 1 ? "day" : "days"}`;
}
