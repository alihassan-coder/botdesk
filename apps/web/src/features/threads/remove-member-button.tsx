import { X } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { actions, useBot, useUser } from "@/data/store";
import type { Participant, Thread } from "@/data/types";

/** The X beside someone in a group's member list. It asks first; a refusal shows as a toast. */
export function RemoveMemberButton({ thread, member }: { thread: Thread; member: Participant }) {
  const bot = useBot(member.type === "bot" ? member.id : undefined);
  const user = useUser(member.type === "user" ? member.id : undefined);
  const name = bot?.name ?? user?.name ?? "them";

  const remove = async () => {
    const result = await actions.removeFromGroup(thread.id, member);
    if (!result.ok) toast.error(result.error);
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={`Remove ${name} from the group`}
          title={`Remove ${name}`}
          className="tap-target text-muted-foreground opacity-100 hover:text-foreground focus-visible:opacity-100 data-[state=open]:opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover/member:opacity-100"
        >
          <X />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove {name} from {thread.title}?</AlertDialogTitle>
          <AlertDialogDescription>
            {member.type === "user" ? "They lose access to this chat." : "It stops what it's doing here and no longer replies in this chat."}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={remove}>Remove</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
