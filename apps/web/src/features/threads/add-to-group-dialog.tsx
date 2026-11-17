import { useState, useTransition } from "react";
import { UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { FieldError, FieldGroup } from "@/components/ui/field";
import { actions, useBots, useUsers } from "@/data/store";
import type { Thread } from "@/data/types";
import { BotAvatar, MemberAvatar } from "@/features/bots/bot-avatar";
import { GroupPickList } from "./group-pick-list";

/** "Add" in a group's details: pick bots and teammates who aren't in it yet. */
export function AddToGroupDialog({ thread }: { thread: Thread }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="self-start">
          <UserPlus data-icon="inline-start" />
          Add people or bots
        </Button>
      </DialogTrigger>
      <DialogContent className="flex max-h-[min(40rem,calc(100svh-2rem))] flex-col">
        {/* Remounted on every open, so nothing starts ticked. */}
        {open && <AddForm thread={thread} onDone={() => setOpen(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function AddForm({ thread, onDone }: { thread: Thread; onDone: () => void }) {
  const isIn = (type: "user" | "bot", id: string) => thread.participants.some((p) => p.type === type && p.id === id);
  const bots = useBots().filter((b) => !isIn("bot", b.id));
  const people = useUsers().filter((u) => !isIn("user", u.id));
  const [botIds, setBotIds] = useState<string[]>([]);
  const [userIds, setUserIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, startSaving] = useTransition();

  const toggle = (setIds: typeof setBotIds) => (id: string) => {
    setError(null);
    setIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  };

  return (
    <form
      className="flex min-h-0 flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        startSaving(async () => {
          const result = await actions.addToGroup(thread.id, { userIds, botIds });
          if (!result.ok) return setError(result.error);
          onDone();
        });
      }}
    >
      <DialogHeader>
        <DialogTitle>Add to {thread.title}</DialogTitle>
        <DialogDescription>They see the group&apos;s messages, including earlier ones.</DialogDescription>
      </DialogHeader>
      <FieldGroup className="-mx-2 min-h-0 gap-4 overflow-y-auto px-2">
        {bots.length === 0 && people.length === 0 && (
          <p className="text-sm text-muted-foreground">Everyone on your team is in this group already.</p>
        )}
        {bots.length > 0 && (
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
      {error && <FieldError>{error}</FieldError>}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
        <Button type="submit" disabled={saving || botIds.length + userIds.length === 0}>{saving ? "Adding…" : "Add"}</Button>
      </DialogFooter>
    </form>
  );
}
