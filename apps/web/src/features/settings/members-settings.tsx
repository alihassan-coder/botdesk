"use client";

import { useState } from "react";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { actions, useCurrentUser, useUsers } from "@/data/store";
import type { User } from "@/data/types";
import { MemberAvatar } from "@/features/bots/bot-avatar";
import { SettingsSection } from "./settings-shell";

const ROLES: { value: User["role"]; label: string }[] = [
  { value: "admin", label: "Admin" },
  { value: "member", label: "Member" },
];

/** Settings → Members: who's in the org and what they can do. Owners can't be demoted here. */
export function MembersSettings() {
  const users = useUsers();
  const me = useCurrentUser();

  return (
    <SettingsSection title="Members" description="Admins manage bots, keys and security. Members chat with bots and approve their own." action={<InviteDialog />}>
      <ul className="flex flex-col divide-y rounded-2xl border">
        {users.map((u) => (
          <li key={u.id} className="flex items-center gap-3 p-3">
            <MemberAvatar name={u.name} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">
                {u.name} {u.id === me.id && <span className="text-muted-foreground">(you)</span>}
              </p>
              <p className="truncate text-xs text-muted-foreground">{u.email}</p>
            </div>
            {u.role === "owner" ? (
              <span className="w-32 px-3 text-sm text-muted-foreground">Owner</span>
            ) : (
              <Select value={u.role} onValueChange={(role) => actions.changeMemberRole(u.id, role as User["role"])}>
                <SelectTrigger className="w-32" aria-label={`Role for ${u.name}`}><SelectValue /></SelectTrigger>
                <SelectContent>{ROLES.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}</SelectContent>
              </Select>
            )}
          </li>
        ))}
      </ul>
    </SettingsSection>
  );
}

function InviteDialog() {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<User["role"]>("member");
  const valid = /^\S+@\S+\.\S+$/.test(email);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm"><UserPlus /> Invite</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite someone</DialogTitle>
          <DialogDescription>They&apos;ll get an email with a link to join.</DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!valid) return;
            actions.inviteMember(email, role);
            toast.success(`Invited ${email}`);
            setEmail("");
            setOpen(false);
          }}
        >
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="invite-email">Email</FieldLabel>
              <Input id="invite-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@company.com" />
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
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={!valid}>Send invite</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
