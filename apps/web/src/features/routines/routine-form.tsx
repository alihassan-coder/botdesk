"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { describeSchedule, fromCron, isCronLine, toCron, type Schedule } from "@/lib/schedule";
import { actions, useBots, useIsDemo } from "@/data/store";
import type { Routine } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { API_KINDS, DEMO_KINDS, SchedulePicker } from "./schedule-picker";
import { StepsEditor } from "./steps-editor";

const noSubscribe = () => () => {};
/** The browser's time zone, known only in the browser (the server renders without it). */
const useBrowserTimeZone = () =>
  useSyncExternalStore(noSubscribe, () => Intl.DateTimeFormat().resolvedOptions().timeZone, () => undefined);

/**
 * Create or edit a routine. On the API: who runs it, what to do (in plain words) and when (a
 * preset or a cron line, in your time zone). The demo also keeps a step list.
 */
export function RoutineForm({ routine }: { routine?: Routine }) {
  const router = useRouter();
  const isDemo = useIsDemo();
  const bots = useBots();
  const browserZone = useBrowserTimeZone();
  const [name, setName] = useState(routine?.name ?? "");
  const [botId, setBotId] = useState(routine?.botId || bots[0]?.id || "");
  const [description, setDescription] = useState(routine?.description ?? "");
  const [schedule, setSchedule] = useState<Schedule>(routine?.cron ? fromCron(routine.cron) : { kind: "weekdays", time: "09:00" });
  const [steps, setSteps] = useState(routine?.steps.length ? routine.steps : [""]);
  const [enabled, setEnabled] = useState(routine?.enabled ?? true);
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);

  const timeZone = routine?.timezone ?? browserZone;
  const cleanSteps = steps.map((s) => s.trim()).filter(Boolean);
  const bot = bots.find((b) => b.id === botId);
  const missing = {
    name: !name.trim(),
    bot: !bot,
    steps: isDemo && cleanSteps.length === 0,
    what: !isDemo && !description.trim(),
    cron: schedule.kind === "cron" && !isCronLine(schedule.cron),
  };

  async function save() {
    if (!bot || Object.values(missing).some(Boolean)) return setShowErrors(true);
    const input = {
      botId: bot.id, name: name.trim(), description: description.trim(), schedule: describeSchedule(schedule),
      steps: isDemo ? cleanSteps : [], enabled,
      ...(isDemo ? {} : { cron: toCron(schedule), timezone: timeZone }),
    };
    setSaving(true);
    const result = routine ? await actions.updateRoutine(routine.id, input) : await actions.createRoutine(input);
    setSaving(false);
    if (!result.ok) return void toast.error(result.error);
    toast.success(routine ? `“${input.name}” saved.` : `“${input.name}” saved. ${bot.name} will run it ${input.schedule.toLowerCase()}.`);
    router.push("/routines");
  }

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
      className="mx-auto flex max-w-2xl flex-col gap-8 p-4 md:p-8"
    >
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">{routine ? "Edit routine" : "Create a routine"}</h2>
        <p className="mt-1 text-sm text-muted-foreground">A job a bot does again and again. It still asks before anything risky, every time.</p>
      </div>

      <FieldGroup>
        <Field data-invalid={showErrors && missing.name}>
          <FieldLabel htmlFor="routine-name">Name</FieldLabel>
          <Input id="routine-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Friday expense report" />
          {showErrors && missing.name && <FieldError>Give the routine a name.</FieldError>}
        </Field>
        <Field data-invalid={showErrors && missing.bot}>
          <FieldLabel htmlFor="routine-bot">Who runs it</FieldLabel>
          <Select value={botId} onValueChange={setBotId}>
            <SelectTrigger id="routine-bot" className="w-full"><SelectValue placeholder="Pick a bot" /></SelectTrigger>
            <SelectContent>
              {bots.map((b) => (
                <SelectItem key={b.id} value={b.id}>
                  <BotAvatar name={b.name} color={b.avatarColor} size="sm" /> {b.name} <span className="text-muted-foreground">· {b.role}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {showErrors && missing.bot && (
            <FieldError>
              Routines need a bot to run them. <Link href="/bots/new" className="underline">Create a bot</Link> first.
            </FieldError>
          )}
        </Field>
        <Field data-invalid={showErrors && missing.what}>
          <FieldLabel htmlFor="routine-description">{isDemo ? "What it does" : "What to do"}</FieldLabel>
          {!isDemo && <FieldDescription>The bot reads this each time, in your chat with it, and replies there.</FieldDescription>}
          <Textarea
            id="routine-description" value={description} onChange={(e) => setDescription(e.target.value)} rows={isDemo ? 2 : 4}
            placeholder={isDemo ? "One sentence, so the team knows what this is." : "e.g. Sum up yesterday's support emails and list anything urgent."}
          />
          {showErrors && missing.what && <FieldError>Say what the bot should do.</FieldError>}
        </Field>
        {/* These labels name a group of controls, not one input, so the group points at them. */}
        <Field aria-labelledby="routine-when" data-invalid={showErrors && missing.cron}>
          <FieldLabel id="routine-when">When</FieldLabel>
          <SchedulePicker value={schedule} onChange={setSchedule} kinds={isDemo ? DEMO_KINDS : API_KINDS} timeZone={isDemo ? undefined : timeZone} />
          {showErrors && missing.cron && <FieldError>A cron line has 5 parts: minute hour day month weekday.</FieldError>}
        </Field>
        {isDemo && (
          <Field data-invalid={showErrors && missing.steps} aria-labelledby="routine-steps">
            <FieldLabel id="routine-steps">Steps</FieldLabel>
            <FieldDescription>In order. Plain words are fine; the bot works out the details.</FieldDescription>
            <StepsEditor steps={steps} onChange={setSteps} />
            {showErrors && missing.steps && <FieldError>Add at least one step.</FieldError>}
          </Field>
        )}
        <Field orientation="horizontal">
          <Switch id="routine-enabled" checked={enabled} onCheckedChange={setEnabled} />
          <FieldLabel htmlFor="routine-enabled">{routine ? "Running on its schedule" : "Start running right away"}</FieldLabel>
        </Field>
      </FieldGroup>

      <div className="flex gap-2 border-t pt-6">
        <Button type="submit" disabled={saving}>Save routine</Button>
        <Button asChild variant="ghost">
          <Link href="/routines">Cancel</Link>
        </Button>
      </div>
    </form>
  );
}
