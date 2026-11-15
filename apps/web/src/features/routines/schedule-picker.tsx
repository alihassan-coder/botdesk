import { CalendarClock } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { describeSchedule, WEEKDAYS, type Schedule, type Weekday } from "@/lib/schedule";

type Kind = Schedule["kind"];

const LABELS: Record<Kind, string> = {
  daily: "Every day",
  weekdays: "Weekdays",
  weekly: "Every week",
  monthly: "Every month",
  hourly: "Every hour",
  cron: "Custom (cron)",
  trigger: "When a new email arrives",
};

/** What the demo offers, and what the API runs (a cron line in your time zone). */
export const DEMO_KINDS: Kind[] = ["daily", "weekdays", "weekly", "monthly", "trigger"];
export const API_KINDS: Kind[] = ["daily", "weekdays", "weekly", "hourly", "cron"];

/** When a routine runs: how often, which day, what time. Shows the result as a sentence. */
export function SchedulePicker({
  value, onChange, kinds = DEMO_KINDS, timeZone,
}: { value: Schedule; onChange: (s: Schedule) => void; kinds?: Kind[]; timeZone?: string }) {
  const time = "time" in value ? value.time : "09:00";
  const day: Weekday = value.kind === "weekly" ? value.day : "Monday";

  function changeKind(kind: Kind) {
    if (kind === "trigger") onChange({ kind, trigger: "new-email" });
    else if (kind === "weekly") onChange({ kind, day, time });
    else if (kind === "hourly") onChange({ kind });
    else if (kind === "cron") onChange({ kind, cron: "0 9 * * 1-5" });
    else onChange({ kind, time });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <Select value={value.kind} onValueChange={(k) => changeKind(k as Kind)}>
          <SelectTrigger className="w-56" aria-label="How often"><SelectValue /></SelectTrigger>
          <SelectContent>{kinds.map((k) => <SelectItem key={k} value={k}>{LABELS[k]}</SelectItem>)}</SelectContent>
        </Select>
        {value.kind === "weekly" && (
          <Select value={day} onValueChange={(d) => onChange({ kind: "weekly", day: d as Weekday, time })}>
            <SelectTrigger className="w-40" aria-label="Day"><SelectValue /></SelectTrigger>
            <SelectContent>{WEEKDAYS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
          </Select>
        )}
        {"time" in value && (
          <Input
            type="time"
            aria-label="Time"
            value={time}
            onChange={(e) => e.target.value && onChange({ ...value, time: e.target.value } as Schedule)}
            className="w-36"
          />
        )}
        {value.kind === "cron" && (
          <Input
            aria-label="Cron line"
            value={value.cron}
            onChange={(e) => onChange({ kind: "cron", cron: e.target.value })}
            placeholder="minute hour day month weekday"
            className="w-56 font-mono"
            spellCheck={false}
          />
        )}
      </div>
      <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <CalendarClock className="size-4" /> Runs: <span className="font-medium text-foreground">{describeSchedule(value)}</span>
        {timeZone && <span>· {timeZone} time</span>}
      </p>
    </div>
  );
}
