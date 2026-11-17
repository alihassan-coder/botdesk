import { useState, useTransition } from "react";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { actions } from "@/data/store";
import type { Thread } from "@/data/types";

/** "Rename" in a group's details: a pencil button that opens a small form with the current name. */
export function RenameGroupDialog({ thread }: { thread: Thread }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="Rename group" title="Rename group">
          <Pencil />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        {/* Remounted on every open, so it starts from the group's current name. */}
        {open && <RenameForm thread={thread} onDone={() => setOpen(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function RenameForm({ thread, onDone }: { thread: Thread; onDone: () => void }) {
  const [title, setTitle] = useState(thread.title);
  const [error, setError] = useState<string | null>(null);
  const [saving, startSaving] = useTransition();
  const unchanged = title.trim() === thread.title;

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (unchanged) return onDone();
        startSaving(async () => {
          const result = await actions.renameGroup(thread.id, title);
          if (!result.ok) return setError(result.error);
          onDone();
        });
      }}
    >
      <DialogHeader>
        <DialogTitle>Rename group</DialogTitle>
        <DialogDescription>Everyone in the group sees the new name.</DialogDescription>
      </DialogHeader>
      <Field data-invalid={error ? true : undefined}>
        <FieldLabel htmlFor="group-name">Name</FieldLabel>
        <Input
          id="group-name"
          value={title}
          maxLength={120}
          autoFocus
          aria-invalid={error ? true : undefined}
          onChange={(e) => {
            setTitle(e.target.value);
            setError(null);
          }}
        />
        {error && <FieldError>{error}</FieldError>}
      </Field>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
        <Button type="submit" disabled={saving || title.trim() === ""}>{saving ? "Saving…" : "Save"}</Button>
      </DialogFooter>
    </form>
  );
}
