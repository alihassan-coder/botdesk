"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { FolderOpen, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel, FieldTitle } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { actions, useCurrentUser, useOrg, useTemplates, type NewBotInput } from "@/data/store";
import type { SecurityLevel, Template } from "@/data/types";
import { strictestLevel } from "@/lib/security-level";
import { PageHeader } from "@/features/shell/page-header";
import { BotAvatar } from "./bot-avatar";
import { BotPreview } from "./bot-preview";
import { ColorPicker } from "./color-picker";
import { ModelPicker } from "./model-picker";
import { SecurityLevelPicker } from "./security-level-picker";

/** The most a member may give a new bot; owners and admins can set any budget (the API checks too). */
const MEMBER_MAX_BUDGET_USD = 50;

const BLANK: NewBotInput = {
  name: "", role: "", description: "", avatarColor: "indigo", instructions: "",
  modelId: "", securityLevel: "ask-before-acting", computerMode: "own", monthlyBudgetUsd: 25,
};

/** A template's job as a starting point: its name, role, words, colour and instructions, at its level or the org's default, whichever is stricter (as hiring it would). */
function fromTemplate(t: Template, orgDefault: SecurityLevel): Partial<NewBotInput> {
  const { name, role, description, avatarColor, instructions } = t;
  return { name, role, description, avatarColor, instructions, securityLevel: strictestLevel(t.securityLevel, orgDefault) };
}

/** /bots/new — build a bot from scratch (or start from a template), with a live preview. */
export function CreateBotScreen() {
  const router = useRouter();
  const templates = useTemplates();
  const { defaultSecurityLevel: defaultLevel, maxSecurityLevel: ceiling } = useOrg();
  // New bots start at the org's default (Settings → Security).
  const [bot, setBot] = useState(() => ({ ...BLANK, securityLevel: defaultLevel }));
  const [showErrors, setShowErrors] = useState(false);
  const [creating, startCreating] = useTransition();
  const budgetLimit = useCurrentUser().role === "member" ? MEMBER_MAX_BUDGET_USD : undefined;
  const update = <K extends keyof NewBotInput>(key: K, value: NewBotInput[K]) => setBot((b) => ({ ...b, [key]: value }));

  const missing = { name: !bot.name.trim(), role: !bot.role.trim() };

  function create() {
    if (missing.name || missing.role) return setShowErrors(true);
    startCreating(async () => {
      const result = await actions.createBot({ ...bot, name: bot.name.trim(), role: bot.role.trim() });
      if (!result.ok) return void toast.error(result.error);
      toast.success(`${bot.name.trim()} is ready. Say hello.`);
      router.push(`/chat/${result.threadId}`);
    });
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="New bot" />
      <div className="flex-1 overflow-y-auto">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create();
          }}
          noValidate className="mx-auto grid max-w-5xl gap-8 p-4 md:p-8 lg:grid-cols-[1fr_320px]">
          <div className="flex flex-col gap-8">
            <section>
              <h2 className="mb-1 text-2xl font-semibold tracking-tight">Create a bot</h2>
              <p className="text-sm text-muted-foreground">A teammate with its own job, tools and limits. Start from scratch, or pick a template.</p>
              <div className="mt-4 flex flex-wrap gap-2" aria-label="Start from a template">
                {templates.map((t) => (
                  <button key={t.id} type="button" onClick={() => setBot({ ...bot, ...fromTemplate(t, defaultLevel) })}
                    className="flex shrink-0 items-center gap-2 rounded-full border py-1 pr-3 pl-1 text-sm hover:bg-muted">
                    <BotAvatar name={t.name} color={t.avatarColor} size="sm" className="[&>span]:rounded-full" /> {t.name}
                  </button>
                ))}
              </div>
            </section>

            <Section title="Who it is">
              <Field data-invalid={showErrors && missing.name}>
                <FieldLabel htmlFor="bot-name">Name</FieldLabel>
                <Input id="bot-name" value={bot.name} onChange={(e) => update("name", e.target.value)} placeholder="e.g. Inbox Manager" aria-invalid={showErrors && missing.name} />
                {showErrors && missing.name && <FieldError>Give your bot a name.</FieldError>}
              </Field>
              <Field data-invalid={showErrors && missing.role}>
                <FieldLabel htmlFor="bot-role">Role</FieldLabel>
                <Input id="bot-role" value={bot.role} onChange={(e) => update("role", e.target.value)} placeholder="e.g. Email triage" aria-invalid={showErrors && missing.role} />
                {showErrors && missing.role && <FieldError>Say what job it does.</FieldError>}
              </Field>
              <Field>
                <FieldLabel>Colour</FieldLabel>
                <ColorPicker value={bot.avatarColor} onChange={(c) => update("avatarColor", c)} />
              </Field>
              <Field>
                <FieldLabel htmlFor="bot-description">What it does</FieldLabel>
                <Textarea id="bot-description" value={bot.description} onChange={(e) => update("description", e.target.value)} rows={2} placeholder="One or two sentences. It introduces itself with this." />
              </Field>
            </Section>

            <Section title="How it works">
              <Field>
                <FieldLabel htmlFor="bot-instructions">Instructions</FieldLabel>
                <Textarea id="bot-instructions" value={bot.instructions} onChange={(e) => update("instructions", e.target.value)} rows={4} placeholder="How it should work, what to avoid, when to ask you." />
              </Field>
              <Field>
                <FieldLabel htmlFor="bot-model">Model</FieldLabel>
                <ModelPicker id="bot-model" value={bot.modelId} onChange={(v) => update("modelId", v)} />
              </Field>
              {/* Every bot gets Files (ADR 0017); the browser isn't built yet, so there's nothing to choose. */}
              <Field>
                <FieldTitle>Computer</FieldTitle>
                <ul className="flex flex-col gap-1.5 text-sm">
                  <li className="flex items-center gap-2"><FolderOpen className="size-4 text-muted-foreground" aria-hidden /> Gets its own folder for files</li>
                  <li className="flex flex-wrap items-center gap-2 text-muted-foreground">
                    <Globe className="size-4" aria-hidden /> A browser for websites with no integration <Badge variant="secondary">Coming soon</Badge>
                  </li>
                </ul>
              </Field>
            </Section>

            <Section title="What it may do">
              <SecurityLevelPicker value={bot.securityLevel} max={ceiling} onChange={(l) => update("securityLevel", l)} />
              <Field>
                <FieldLabel htmlFor="bot-budget">Monthly budget (USD)</FieldLabel>
                <Input id="bot-budget" type="number" min={budgetLimit ? 1 : 0} max={budgetLimit} step={5} value={bot.monthlyBudgetUsd} className="max-w-40"
                  onChange={(e) => update("monthlyBudgetUsd", Math.min(budgetLimit ?? Infinity, Math.max(budgetLimit ? 1 : 0, Number(e.target.value))))} />
                <FieldDescription>
                  The bot pauses when it reaches this, and tells you.
                  {budgetLimit ? ` Up to $${budgetLimit}: only owners and admins can set more.` : null}
                </FieldDescription>
              </Field>
            </Section>
          </div>

          <aside className="flex flex-col gap-3 lg:sticky lg:top-8 lg:self-start">
            <BotPreview bot={bot} />
            <Button type="submit" size="lg" disabled={creating}>{creating ? "Creating…" : "Create bot"}</Button>
            <Button type="button" variant="ghost" onClick={() => router.back()}>Cancel</Button>
          </aside>
        </form>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <h3 className="border-b pb-2 text-sm font-semibold">{title}</h3>
      <FieldGroup>{children}</FieldGroup>
    </section>
  );
}
