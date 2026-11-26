/**
 * Days in a chat, the way a messaging app shows them: "Today", "Yesterday", the weekday within the
 * last week, then the date. Calendar days where you are (your time zone), not 24-hour spans: a
 * message at 23:59 is yesterday's a minute later. Pure: callers pass `now` (and a time zone in tests).
 */

const DAY = 86_400_000;

// Formatting is the slow part, and a chat asks for hundreds of these: one formatter per time zone.
const keyFormats = new Map<string, Intl.DateTimeFormat>();

function keyFormat(timeZone: string | undefined): Intl.DateTimeFormat {
  const id = timeZone ?? "";
  let format = keyFormats.get(id);
  if (!format) {
    format = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" });
    keyFormats.set(id, format);
  }
  return format;
}

/** The calendar day a moment falls on, in `timeZone` (default: this device's): "2026-11-26". */
export function dayKey(iso: string | number, timeZone?: string): string {
  return keyFormat(timeZone).format(new Date(iso)); // en-CA writes dates as YYYY-MM-DD
}

/** Days since 1970 for a "YYYY-MM-DD" key, so two keys subtract to whole days. */
function dayNumber(key: string): number {
  const [year, month, day] = key.split("-").map(Number);
  return Date.UTC(year, month - 1, day) / DAY;
}

/** "Today", "Yesterday", "Tuesday" (within the last week), "November 19", or "December 31, 2025" (another year). */
export function dayLabel(iso: string, now: number, timeZone?: string): string {
  const day = dayKey(iso, timeZone);
  const today = dayKey(now, timeZone);
  const daysAgo = dayNumber(today) - dayNumber(day);
  if (daysAgo <= 0) return "Today"; // a clock a little behind the server's still says today
  if (daysAgo === 1) return "Yesterday";
  const date = new Date(iso);
  if (daysAgo < 7) return date.toLocaleDateString("en-US", { timeZone, weekday: "long" });
  const sameYear = day.slice(0, 4) === today.slice(0, 4);
  return date.toLocaleDateString("en-US", { timeZone, month: "long", day: "numeric", ...(sameYear ? {} : { year: "numeric" }) });
}

/** For each message, whether it's the first of its day in the list (the first one always is). */
export function startsADay(messages: readonly { createdAt: string }[], timeZone?: string): boolean[] {
  let previous: string | null = null;
  return messages.map((message) => {
    const day = dayKey(message.createdAt, timeZone);
    const starts = day !== previous;
    previous = day;
    return starts;
  });
}
