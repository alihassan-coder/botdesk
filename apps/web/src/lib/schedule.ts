/** How often a routine runs, as picked in the routine form. */
export type Schedule =
  | { kind: "daily"; time: string }
  | { kind: "weekdays"; time: string }
  | { kind: "weekly"; day: Weekday; time: string }
  | { kind: "monthly"; time: string }
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
    case "trigger":
      return "When a new email arrives";
  }
}
