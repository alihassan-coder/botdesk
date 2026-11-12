"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Check, Copy, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { actions, isDemoMode, useUsers } from "@/data/store";
import type { User } from "@/data/types";
import { looksLikeEmail } from "@/lib/email";
import { ROLES } from "./roles";

/**
 * Invite someone by email. With the API there's no email sending yet, so the dialog
 * shows the one-time invite link to copy and share. In the demo they join at once.
 */
export function InviteDialog() {
  const [open, setOpen] = useState(false);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);

  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) setInviteUrl(null);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm"><UserPlus /> Invite</Button>
      </DialogTrigger>
      <DialogContent>
        {inviteUrl ? (
          <InviteLink url={inviteUrl} onDone={() => onOpenChange(false)} />
        ) : (
          <InviteForm onInvited={(url) => (url ? setInviteUrl(url) : onOpenChange(false))} onCancel={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function InviteForm({ onInvited, onCancel }: { onInvited: (inviteUrl?: string) => void; onCancel: () => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<User["role"]>("member");
  const [error, setError] = useState<string | null>(null);
  const [sending, startSending] = useTransition();
  const users = useUsers();
  const address = email.trim().toLowerCase();
  const alreadyIn = users.some((u) => u.email.toLowerCase() === address);
  const valid = looksLikeEmail(address) && !alreadyIn;
  const problem = alreadyIn ? `${address} is already in this organization.` : error;

  return (
    <>
      <DialogHeader>
        <DialogTitle>Invite someone</DialogTitle>
        <DialogDescription>
          {isDemoMode() ? "They'll get an email with a link to join." : "You'll get a link to send them. It works once."}
        </DialogDescription>
      </DialogHeader>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!valid) return;
          startSending(async () => {
            const result = await actions.inviteMember(address, role);
            if (!result.ok) return setError(result.error);
            toast.success(`Invited ${address}`);
            onInvited(result.inviteUrl);
          });
        }}
      >
        <FieldGroup>
          <Field data-invalid={!!problem}>
            <FieldLabel htmlFor="invite-email">Email</FieldLabel>
            <Input
              id="invite-email" type="email" value={email} placeholder="teammate@company.com" aria-invalid={!!problem}
              onChange={(e) => { setEmail(e.target.value); setError(null); }}
            />
            {problem && <FieldError>{problem}</FieldError>}
          </Field>
          <Field>
            <FieldLabel htmlFor="invite-role">Role</FieldLabel>
            <Select value={role} onValueChange={(r) => setRole(r as User["role"])}>
              <SelectTrigger id="invite-role" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{ROLES.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
        </FieldGroup>
        <DialogFooter className="mt-6">
          <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button type="submit" disabled={!valid || sending}>{sending ? "Sending…" : "Send invite"}</Button>
        </DialogFooter>
      </form>
    </>
  );
}

/** The invite link is only shown this once, so make copying it the obvious next step. */
function InviteLink({ url, onDone }: { url: string; onDone: () => void }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      toast.error("Couldn't copy. Select the link and copy it yourself.");
    }
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>Send them this link</DialogTitle>
        <DialogDescription>
          Anyone signed in with the invited email can use it to join. You won&apos;t see it again after closing.
        </DialogDescription>
      </DialogHeader>
      <div className="flex gap-2">
        {/* Focused and selected on open: shows the whole token and is ready for Ctrl+C. */}
        <Input readOnly autoFocus value={url} aria-label="Invite link" onFocus={(e) => e.currentTarget.select()} className="font-mono text-xs" />
        <Button type="button" variant="outline" onClick={copy}>
          {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <DialogFooter>
        <Button type="button" onClick={onDone}>Done</Button>
      </DialogFooter>
    </>
  );
}
