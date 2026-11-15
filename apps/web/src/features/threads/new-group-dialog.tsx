"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { actions, useBots, useCurrentUser, useUsers } from "@/data/store";
import { BotAvatar, MemberAvatar } from "@/features/bots/bot-avatar";
import { GroupPickList } from "./group-pick-list";

/**
 * "New group" from the sidebar: name it, pick bots and teammates, then open the new chat.
 * You're always in it. In a group, the bots you @mention are the ones who reply; a message that
 * mentions no bot goes to the lead (the first bot picked, unless you choose another).
 */
export function NewGroupDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (open: boolean) => void; onCreated?: () => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[min(40rem,calc(100svh-2rem))] flex-col">
        {/* Remounted on every open, so the form starts empty. */}
        {open && <NewGroupForm onCancel={() => onOpenChange(false)} onCreated={() => { onOpenChange(false); onCreated?.(); }} />}
      </DialogContent>
    </Dialog>
  );
}

function NewGroupForm({ onCancel, onCreated }: { onCancel: () => void; onCreated: () => void }) {
  const router = useRouter();
  const bots = useBots();
  const me = useCurrentUser();
  const people = useUsers().filter((u) => u.id !== me.id);
  const [title, setTitle] = useState("");
  const [botIds, setBotIds] = useState<string[]>([]);
  const [userIds, setUserIds] = useState<string[]>([]);
  const [chosenLead, setChosenLead] = useState<string>();
  // The lead you chose while it's still picked; otherwise the first bot picked.
  const leadBotId = chosenLead && botIds.includes(chosenLead) ? chosenLead : botIds[0];
  const [error, setError] = useState<string | null>(null);
  const [creating, startCreating] = useTransition();
  const ready = title.trim() !== "" && botIds.length > 0;

  const toggle = (setIds: typeof setBotIds) => (id: string) => {
    setError(null);
    setIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  };

  return (
    <form
      className="flex min-h-0 flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (!ready) return;
        startCreating(async () => {
          const result = await actions.createGroup({ title, botIds, userIds, leadBotId });
          if (!result.ok) return setError(result.error);
          router.push(`/chat/${result.threadId}`);
          onCreated();
        });
      }}
    >
      <DialogHeader>
        <DialogTitle>New group</DialogTitle>
        <DialogDescription>You&apos;re in it too. Bots reply when you @mention them; the lead answers everything else.</DialogDescription>
      </DialogHeader>
      <Field>
        <FieldLabel htmlFor="group-title">Name</FieldLabel>
        <Input id="group-title" value={title} maxLength={120} placeholder="Launch crew" autoFocus onChange={(e) => { setTitle(e.target.value); setError(null); }} />
      </Field>
      <FieldGroup className="-mx-2 min-h-0 gap-4 overflow-y-auto px-2">
        {bots.length === 0 ? (
          <p className="text-sm text-muted-foreground">Your team has no bots yet. Create one first, then start a group with it.</p>
        ) : (
          <GroupPickList
            legend="Bots"
            options={bots.map((b) => ({ id: b.id, name: b.name, detail: b.role, avatar: <BotAvatar name={b.name} color={b.avatarColor} size="sm" /> }))}
            picked={botIds}
            onToggle={toggle(setBotIds)}
          />
        )}
        {people.length > 0 && (
          <GroupPickList
            legend="People"
            options={people.map((u) => ({ id: u.id, name: u.name, detail: `@${u.handle}`, avatar: <MemberAvatar name={u.name} size="sm" /> }))}
            picked={userIds}
            onToggle={toggle(setUserIds)}
          />
        )}
      </FieldGroup>
      {botIds.length > 1 && (
        <Field>
          <FieldLabel htmlFor="group-lead">Lead</FieldLabel>
          <NativeSelect id="group-lead" className="w-full" value={leadBotId} onChange={(e) => setChosenLead(e.target.value)}>
            {botIds.map((botId) => (
              <NativeSelectOption key={botId} value={botId}>{bots.find((b) => b.id === botId)?.name}</NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
      )}
      {error && <FieldError>{error}</FieldError>}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={!ready || creating}>{creating ? "Creating…" : "Create"}</Button>
      </DialogFooter>
    </form>
  );
}
