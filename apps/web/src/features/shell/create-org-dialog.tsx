import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { actions } from "@/data/store";

/**
 * "New organization" from the org switcher: you own the new one, and the app switches to it
 * (going home, since the open chat belongs to the old one). Controlled, so the menu that opens it can close first.
 */
export function CreateOrgDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, startCreating] = useTransition();

  const change = (next: boolean) => {
    onOpenChange(next);
    if (!next) {
      setName("");
      setError(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New organization</DialogTitle>
          <DialogDescription>A separate team with its own bots, chats, keys and members. You&apos;ll be its owner.</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!name.trim()) return;
            startCreating(async () => {
              const result = await actions.createOrg(name);
              if (!result.ok) return setError(result.error);
              toast.success(`Created ${name.trim()}`);
              change(false);
              router.push("/");
            });
          }}
        >
          <FieldGroup>
            <Field data-invalid={!!error}>
              <FieldLabel htmlFor="new-org-name">Name</FieldLabel>
              <Input
                id="new-org-name" value={name} maxLength={120} placeholder="Acme Labs" autoComplete="organization" aria-invalid={!!error}
                onChange={(e) => {
                  setName(e.target.value);
                  setError(null);
                }}
              />
              {error && <FieldError>{error}</FieldError>}
            </Field>
          </FieldGroup>
          <DialogFooter className="mt-6">
            <Button type="button" variant="outline" onClick={() => change(false)}>Cancel</Button>
            <Button type="submit" disabled={!name.trim() || creating}>{creating ? "Creating…" : "Create organization"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
