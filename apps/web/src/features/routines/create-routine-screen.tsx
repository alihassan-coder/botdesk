"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { describeSchedule, type Schedule } from "@/lib/schedule";
import { actions, useBots } from "@/data/store";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { PageHeader } from "@/features/shell/page-header";
import { SchedulePicker } from "./schedule-picker";
import { StepsEditor } from "./steps-editor";

/** /routines/new — a job a bot repeats: who runs it, when, and the steps it follows. */
export function CreateRoutineScreen() {
  const router = useRouter();
  const bots = useBots();
  const [name, setName] = useState("");
  const [botId, setBotId] = useState(bots[0]?.id ?? "");
  const [description, setDescription] = useState("");
  const [schedule, setSchedule] = useState<Schedule>({ kind: "weekdays", time: "09:00" });
  const [steps, setSteps] = useState([""]);
  const [enabled, setEnabled] = useState(true);
  const [showErrors, setShowErrors] = useState(false);

  const cleanSteps = steps.map((s) => s.trim()).filter(Boolean);
  const missing = { name: !name.trim(), steps: cleanSteps.length === 0 };

  function save() {
    if (missing.name || missing.steps) return setShowErrors(true);
    actions.createRoutine({ botId, name: name.trim(), description: description.trim(), schedule: describeSchedule(schedule), steps: cleanSteps, enabled });
    toast.success(`“${name.trim()}” saved. ${bots.find((b) => b.id === botId)?.name} confirmed it in your chat.`);
    router.push("/routines");
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="New routine" />
      <div className="flex-1 overflow-y-auto">
        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
          className="mx-auto flex max-w-2xl flex-col gap-8 p-4 md:p-8"
        >
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Create a routine</h2>
            <p className="mt-1 text-sm text-muted-foreground">A job a bot does again and again. It still asks before anything risky, every time.</p>
          </div>

          <FieldGroup>
            <Field data-invalid={showErrors && missing.name}>
              <FieldLabel htmlFor="routine-name">Name</FieldLabel>
              <Input id="routine-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Friday expense report" />
              {showErrors && missing.name && <FieldError>Give the routine a name.</FieldError>}
            </Field>
            <Field>
              <FieldLabel htmlFor="routine-bot">Who runs it</FieldLabel>
              <Select value={botId} onValueChange={setBotId}>
                <SelectTrigger id="routine-bot" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {bots.map((b) => (
                    <SelectItem key={b.id} value={b.id}>
                      <BotAvatar name={b.name} color={b.avatarColor} size="sm" /> {b.name} <span className="text-muted-foreground">· {b.role}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="routine-description">What it does</FieldLabel>
              <Textarea id="routine-description" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} placeholder="One sentence, so the team knows what this is." />
            </Field>
            <Field>
              <FieldLabel>When</FieldLabel>
              <SchedulePicker value={schedule} onChange={setSchedule} />
            </Field>
            <Field data-invalid={showErrors && missing.steps}>
              <FieldLabel>Steps</FieldLabel>
              <FieldDescription>In order. Plain words are fine; the bot works out the details.</FieldDescription>
              <StepsEditor steps={steps} onChange={setSteps} />
              {showErrors && missing.steps && <FieldError>Add at least one step.</FieldError>}
            </Field>
            <Field orientation="horizontal">
              <Switch id="routine-enabled" checked={enabled} onCheckedChange={setEnabled} />
              <FieldLabel htmlFor="routine-enabled">Start running right away</FieldLabel>
            </Field>
          </FieldGroup>

          <div className="flex gap-2 border-t pt-6">
            <Button type="submit">Save routine</Button>
            <Button type="button" variant="ghost" onClick={() => router.back()}>Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
