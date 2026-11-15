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

/** "07:00" → "7 AM", "13:30" → "1:30 PM". */
export function formatTime(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  const suffix = h < 12 ? "AM" : "PM";
  return m ? `${hour12}:${String(m).padStart(2, "0")} ${suffix}` : `${hour12} ${suffix}`;
}

/** The schedule as the sentence shown everywhere: "Weekdays at 7 AM", "Every Friday at 5 PM". */
export function describeSchedule(s: Schedule): string {
  switch (s.kind) {
    case "daily":
      return `Every day at ${formatTime(s.time)}`;
    case "weekdays":
      return `Weekdays at ${formatTime(s.time)}`;
    case "weekly":
      return `Every ${s.day} at ${formatTime(s.time)}`;
    case "monthly":
      return `On the 1st of every month at ${formatTime(s.time)}`;
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

function hourMinute(time: string): string {
  const [h, m] = time.split(":").map(Number);
  return `${m} ${h}`;
}

/** The schedule as a cron line. The demo's monthly and email kinds have none. */
export function toCron(s: Schedule): string {
  switch (s.kind) {
    case "daily":
      return `${hourMinute(s.time)} * * *`;
    case "weekdays":
      return `${hourMinute(s.time)} * * 1-5`;
    case "weekly":
      return `${hourMinute(s.time)} * * ${cronDay(s.day)}`;
    case "hourly":
      return "0 * * * *";
    case "cron":
      return s.cron.trim().split(/\s+/).join(" ");
    case "monthly":
      return `${hourMinute(s.time)} 1 * *`;
    case "trigger":
      return "";
  }
}

const NUMBER = /^\d{1,2}$/;
const pad = (n: string) => n.padStart(2, "0");

/** A cron line as the picker's preset when it is one, else as a custom line. */
export function fromCron(line: string): Schedule {
  const cron = line.trim().split(/\s+/).join(" ");
  const [minute, hour, day, month, weekday] = cron.split(" ");
  if (cron === "0 * * * *") return { kind: "hourly" };
  if (NUMBER.test(minute ?? "") && NUMBER.test(hour ?? "") && day === "*" && month === "*") {
    const time = `${pad(hour)}:${pad(minute)}`;
    if (weekday === "*") return { kind: "daily", time };
    if (weekday === "1-5") return { kind: "weekdays", time };
    if (/^[0-7]$/.test(weekday)) return { kind: "weekly", day: WEEKDAYS[(Number(weekday) + 6) % 7], time };
  }
  return { kind: "cron", cron };
}

/** "Weekdays at 7:30 AM", or "Custom schedule: …" with the line itself. */
export const describeCron = (line: string) => describeSchedule(fromCron(line));
