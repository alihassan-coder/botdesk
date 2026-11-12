import { useState, useTransition } from "react";
import { toast } from "sonner";
import { UserMinus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { actions } from "@/data/store";
import type { User } from "@/data/types";
import { MemberAvatar } from "@/features/bots/bot-avatar";
import { canChangeRole, rolesYouCanGive } from "./roles";

type Role = User["role"];

/** One person in Settings → Members, with their role and (if you may) a way to change or remove them. */
export function MemberRow({ member, isMe, yourRole }: { member: User; isMe: boolean; yourRole: Role }) {
  const [saving, startSaving] = useTransition();
  const [confirmingOwner, setConfirmingOwner] = useState(false);
  const editable = canChangeRole(yourRole, member.role);

  const changeRole = (role: Role) =>
    startSaving(async () => {
      const result = await actions.changeMemberRole(member.id, role);
      if (!result.ok) toast.error(result.error);
    });

  // Making an owner can't be undone by an admin, so ask first. Other changes save at once.
  const pickRole = (role: Role) => (role === "owner" ? setConfirmingOwner(true) : changeRole(role));

  return (
    <li className="flex items-center gap-3 p-3">
      <MemberAvatar name={member.name} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">
          {member.name} {isMe && <span className="text-muted-foreground">(you)</span>}
        </p>
        <p className="truncate text-xs text-muted-foreground">{member.email}</p>
      </div>
      {editable ? (
        <Select value={member.role} onValueChange={(role) => pickRole(role as Role)} disabled={saving}>
          <SelectTrigger className="w-32" aria-label={`Role for ${member.name}`}><SelectValue /></SelectTrigger>
          <SelectContent>{rolesYouCanGive(yourRole).map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}</SelectContent>
        </Select>
      ) : (
        <span className="shrink-0 px-3 text-sm text-muted-foreground capitalize sm:w-32">{member.role}</span>
      )}
      {editable && !isMe ? <RemoveMember member={member} /> : <span className="hidden size-9 sm:block" aria-hidden />}
      <ConfirmOwner member={member} open={confirmingOwner} onOpenChange={setConfirmingOwner} onConfirm={() => changeRole("owner")} />
    </li>
  );
}

function ConfirmOwner({ member, open, onOpenChange, onConfirm }: { member: User; open: boolean; onOpenChange: (open: boolean) => void; onConfirm: () => void }) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Make {member.name} an owner?</AlertDialogTitle>
          <AlertDialogDescription>
            Owners can do everything you can, including changing who else is an owner and removing you. Only another owner can undo this.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Make owner</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function RemoveMember({ member }: { member: User }) {
  const remove = async () => {
    const result = await actions.removeMember(member.id);
    if (result.ok) toast.success(`Removed ${member.name}`);
    else toast.error(result.error);
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Remove ${member.name}`}>
          <UserMinus />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove {member.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            They lose access to this organization&apos;s bots and chats straight away. You can invite them again later.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep them</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={remove}>Remove</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
