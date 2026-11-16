/** How often a routine runs, as picked in the routine form. `monthly` and `trigger` are the demo's; `hourly` and `cron` the API's. */
export type Schedule =
  | { kind: "daily"; time: string }
  | { kind: "weekdays"; time: string }
  | { kind: "weekly"; day: Weekday; time: string }
  | { kind: "monthly"; time: string }
  | { kind: "hourly" }
  | { kind: "cron"; cron: string }
  | { kind: "trigger"; trigger: "new-email" };

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;
export type Weekday = (typeof WEEKDAYS)[number];

const HH_MM = /^([01]?\d|2[0-3]):([0-5]\d)$/;

/** "07:30" is a time; "", "9" and "24:00" aren't (a time input that was cleared gives ""). */
export const isTime = (hhmm: string) => HH_MM.test(hhmm);

function parseTime(hhmm: string): { h: number; m: number } | null {
  const match = HH_MM.exec(hhmm);
  return match ? { h: Number(match[1]), m: Number(match[2]) } : null;
}

function clock(h: number, m: number): string {
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  const suffix = h < 12 ? "AM" : "PM";
  return m ? `${hour12}:${String(m).padStart(2, "0")} ${suffix}` : `${hour12} ${suffix}`;
}

/** "07:00" → "7 AM", "13:30" → "1:30 PM"; "" when it isn't a time. */
export function formatTime(hhmm: string): string {
  const time = parseTime(hhmm);
  return time ? clock(time.h, time.m) : "";
}

/** "Every day" + " at 9 AM", or " (pick a time)" while the time is empty. */
const at = (prefix: string, hhmm: string) => (isTime(hhmm) ? `${prefix} at ${formatTime(hhmm)}` : `${prefix} (pick a time)`);

/** The schedule as the sentence shown everywhere: "Weekdays at 7 AM", "Every Friday at 5 PM". */
export function describeSchedule(s: Schedule): string {
  switch (s.kind) {
    case "daily":
      return at("Every day", s.time);
    case "weekdays":
      return at("Weekdays", s.time);
    case "weekly":
      return at(`Every ${s.day}`, s.time);
    case "monthly":
      return at("On the 1st of every month", s.time);
    case "hourly":
      return "Every hour";
    case "cron":
      return `Custom schedule: ${s.cron}`;
    case "trigger":
      return "When a new email arrives";
  }
}

/* ---------- Cron lines (what the API stores: minute hour day month weekday) ---------- */

export const isCronLine = (line: string) => line.trim().split(/\s+/).length === 5;

/** Cron counts weekdays from Sunday = 0. */
const cronDay = (day: Weekday) => (WEEKDAYS.indexOf(day) + 1) % 7;

/** The schedule as a cron line. "" when it has none: the demo's monthly and email kinds, or no time picked yet. */
export function toCron(s: Schedule): string {
  if (s.kind === "hourly") return "0 * * * *";
  if (s.kind === "cron") return s.cron.trim().split(/\s+/).join(" ");
  if (s.kind === "trigger") return "";
  const time = parseTime(s.time);
  if (!time) return "";
  const hm = `${time.m} ${time.h}`;
  switch (s.kind) {
    case "daily":
      return `${hm} * * *`;
    case "weekdays":
      return `${hm} * * 1-5`;
    case "weekly":
      return `${hm} * * ${cronDay(s.day)}`;
    case "monthly":
      return `${hm} 1 * *`;
  }
}

const NUMBER = /^\d{1,2}$/;
const MINUTE_LIST = /^\d{1,2}(,\d{1,2})+$/;
const pad = (n: string) => n.padStart(2, "0");

function presetFor(weekday: string, time: string): Schedule | null {
  if (weekday === "*") return { kind: "daily", time };
  if (weekday === "1-5") return { kind: "weekdays", time };
  if (/^[0-7]$/.test(weekday)) return { kind: "weekly", day: WEEKDAYS[(Number(weekday) + 6) % 7], time };
  return null;
}

/** A cron line as the picker's preset when it is one, else as a custom line. */
export function fromCron(line: string): Schedule {
  const cron = line.trim().split(/\s+/).join(" ");
  const [minute, hour, day, month, weekday] = cron.split(" ");
  if (cron === "0 * * * *") return { kind: "hourly" };
  if (NUMBER.test(minute ?? "") && NUMBER.test(hour ?? "") && day === "*" && month === "*") {
    const preset = presetFor(weekday ?? "", `${pad(hour)}:${pad(minute)}`);
    if (preset) return preset;
  }
  return { kind: "cron", cron };
}

/** "a", "a and b", "a, b and c". */
const list = (items: string[]) => (items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`);

/** Words for lines the presets can't hold but people still write: some minutes of every hour, or several in one hour. */
function describeMinutes(cron: string): string | null {
  const [minute = "", hour = "", day, month, weekday = ""] = cron.split(" ");
  if (day !== "*" || month !== "*" || !(NUMBER.test(minute) || MINUTE_LIST.test(minute))) return null;
  const minutes = [...new Set(minute.split(",").map(Number))].sort((a, b) => a - b);
  if (minutes.some((m) => m > 59)) return null;
  if (hour === "*" && weekday === "*") return `Every hour at ${list(minutes.map((m) => `:${String(m).padStart(2, "0")}`))}`;
  if (!NUMBER.test(hour) || Number(hour) > 23 || minutes.length < 2) return null;
  const preset = presetFor(weekday, "");
  if (!preset) return null;
  const days = describeSchedule(preset).replace(" (pick a time)", "");
  return `${days} at ${list(minutes.map((m) => clock(Number(hour), m)))}`;
}

/** "Weekdays at 7:30 AM", "Every day at 9 AM and 9:30 AM", or "Custom schedule: …" with the line itself. */
export function describeCron(line: string): string {
  const schedule = fromCron(line);
  return (schedule.kind === "cron" && describeMinutes(schedule.cron)) || describeSchedule(schedule);
}
