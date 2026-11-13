import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { actions, type NewBotInput } from "@/data/store";
import type { Bot } from "@/data/types";
import { ColorPicker } from "./color-picker";
import { ModelPicker } from "./model-picker";
import { SecurityLevelPicker } from "./security-level-picker";

type Editable = Omit<NewBotInput, "computerMode">;

/** "Edit" in a bot's details: change who it is, how it works and what it may do. */
export function EditBotDialog({ bot }: { bot: Bot }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm"><Pencil /> Edit</Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit {bot.name}</DialogTitle>
          <DialogDescription>Changes apply to its next task.</DialogDescription>
        </DialogHeader>
        {/* Mounted only while open, so the form starts from the bot's current values each time. */}
        <EditBotForm bot={bot} onDone={() => setOpen(false)} />
      </DialogContent>
    </Dialog>
  );
}

function EditBotForm({ bot, onDone }: { bot: Bot; onDone: () => void }) {
  const [draft, setDraft] = useState<Editable>(() => ({
    name: bot.name, role: bot.role, description: bot.description, avatarColor: bot.avatarColor, instructions: bot.instructions,
    modelId: bot.modelId, securityLevel: bot.securityLevel, monthlyBudgetUsd: bot.monthlyBudgetUsd,
  }));
  const [saving, startSaving] = useTransition();
  const update = <K extends keyof Editable>(key: K, value: Editable[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const nameMissing = !draft.name.trim();

  const save = () =>
    startSaving(async () => {
      const result = await actions.editBot(bot.id, { ...draft, name: draft.name.trim(), role: draft.role.trim() });
      if (!result.ok) return void toast.error(result.error);
      toast.success(`Saved ${draft.name.trim()}`);
      onDone();
    });

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        if (!nameMissing) save();
      }}
      className="flex flex-col gap-5"
    >
      <FieldGroup>
        <Field data-invalid={nameMissing}>
          <FieldLabel htmlFor="edit-bot-name">Name</FieldLabel>
          <Input id="edit-bot-name" value={draft.name} onChange={(e) => update("name", e.target.value)} aria-invalid={nameMissing} />
          {nameMissing && <FieldError>Give your bot a name.</FieldError>}
        </Field>
        <Field>
          <FieldLabel htmlFor="edit-bot-role">Role</FieldLabel>
          <Input id="edit-bot-role" value={draft.role} onChange={(e) => update("role", e.target.value)} />
        </Field>
        <Field>
          <FieldLabel>Colour</FieldLabel>
          <ColorPicker value={draft.avatarColor} onChange={(c) => update("avatarColor", c)} />
        </Field>
        <Field>
          <FieldLabel htmlFor="edit-bot-description">What it does</FieldLabel>
          <Textarea id="edit-bot-description" rows={2} value={draft.description} onChange={(e) => update("description", e.target.value)} />
        </Field>
        <Field>
          <FieldLabel htmlFor="edit-bot-instructions">Instructions</FieldLabel>
          <Textarea id="edit-bot-instructions" rows={4} value={draft.instructions} onChange={(e) => update("instructions", e.target.value)} />
        </Field>
        <Field>
          <FieldLabel htmlFor="edit-bot-model">Model</FieldLabel>
          <ModelPicker id="edit-bot-model" value={draft.modelId} onChange={(v) => update("modelId", v)} />
        </Field>
        <Field>
          <FieldLabel>Security level</FieldLabel>
          <SecurityLevelPicker value={draft.securityLevel} onChange={(l) => update("securityLevel", l)} />
        </Field>
        <Field>
          <FieldLabel htmlFor="edit-bot-budget">Monthly budget (USD)</FieldLabel>
          <Input id="edit-bot-budget" type="number" min={0} step={5} className="max-w-40" value={draft.monthlyBudgetUsd}
            onChange={(e) => update("monthlyBudgetUsd", Math.max(0, Number(e.target.value)))} />
        </Field>
      </FieldGroup>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
        <Button type="submit" disabled={saving || nameMissing}>{saving ? "Saving…" : "Save changes"}</Button>
      </DialogFooter>
    </form>
  );
}
