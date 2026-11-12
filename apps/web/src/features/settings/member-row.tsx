import { useTransition } from "react";
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
import { ROLES } from "./roles";

/** One person in Settings → Members. Owners are shown, not edited, here. */
export function MemberRow({ member, isMe, canManage }: { member: User; isMe: boolean; canManage: boolean }) {
  const [saving, startSaving] = useTransition();
  const editable = canManage && member.role !== "owner";

  const changeRole = (role: User["role"]) =>
    startSaving(async () => {
      const result = await actions.changeMemberRole(member.id, role);
      if (!result.ok) toast.error(result.error);
    });

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
        <Select value={member.role} onValueChange={(role) => changeRole(role as User["role"])} disabled={saving}>
          <SelectTrigger className="w-32" aria-label={`Role for ${member.name}`}><SelectValue /></SelectTrigger>
          <SelectContent>{ROLES.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}</SelectContent>
        </Select>
      ) : (
        <span className="shrink-0 px-3 text-sm text-muted-foreground capitalize sm:w-32">{member.role}</span>
      )}
      {editable && !isMe ? <RemoveMember member={member} /> : <span className="hidden size-9 sm:block" aria-hidden />}
    </li>
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
