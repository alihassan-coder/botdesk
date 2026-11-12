import { CalendarClock } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { describeSchedule, WEEKDAYS, type Schedule, type Weekday } from "@/lib/schedule";

const KINDS: { value: Schedule["kind"]; label: string }[] = [
  { value: "daily", label: "Every day" },
  { value: "weekdays", label: "Weekdays" },
  { value: "weekly", label: "Every week" },
  { value: "monthly", label: "Every month" },
  { value: "trigger", label: "When a new email arrives" },
];

/** When a routine runs: how often, which day, what time. Shows the result as a sentence. */
export function SchedulePicker({ value, onChange }: { value: Schedule; onChange: (s: Schedule) => void }) {
  const time = "time" in value ? value.time : "09:00";
  const day: Weekday = value.kind === "weekly" ? value.day : "Monday";

  function changeKind(kind: Schedule["kind"]) {
    if (kind === "trigger") onChange({ kind, trigger: "new-email" });
    else if (kind === "weekly") onChange({ kind, day, time });
    else onChange({ kind, time });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <Select value={value.kind} onValueChange={(k) => changeKind(k as Schedule["kind"])}>
          <SelectTrigger className="w-56" aria-label="How often"><SelectValue /></SelectTrigger>
          <SelectContent>{KINDS.map((k) => <SelectItem key={k.value} value={k.value}>{k.label}</SelectItem>)}</SelectContent>
        </Select>
        {value.kind === "weekly" && (
          <Select value={day} onValueChange={(d) => onChange({ kind: "weekly", day: d as Weekday, time })}>
            <SelectTrigger className="w-40" aria-label="Day"><SelectValue /></SelectTrigger>
            <SelectContent>{WEEKDAYS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
          </Select>
        )}
        {value.kind !== "trigger" && (
          <Input
            type="time"
            aria-label="Time"
            value={time}
            onChange={(e) => e.target.value && onChange({ ...value, time: e.target.value } as Schedule)}
            className="w-36"
          />
        )}
      </div>
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <CalendarClock className="size-4" /> Runs: <span className="font-medium text-foreground">{describeSchedule(value)}</span>
      </p>
    </div>
  );
}
