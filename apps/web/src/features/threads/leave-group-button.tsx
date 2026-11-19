import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { actions } from "@/data/store";
import type { Thread } from "@/data/types";

/**
 * "Leave group" at the foot of a group's details: anyone in it may. The group leaves your list,
 * so we head home. The last person out deletes it, which the confirm says.
 */
export function LeaveGroupButton({ thread }: { thread: Thread }) {
  const router = useRouter();
  const last = thread.participants.filter((p) => p.type === "user").length === 1;

  const leave = async () => {
    const result = await actions.leaveGroup(thread.id);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`You left ${thread.title}`);
    router.push("/");
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="sm" className="self-start text-destructive hover:text-destructive">
          <LogOut /> Leave group
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Leave {thread.title}?</AlertDialogTitle>
          <AlertDialogDescription>
            {last
              ? "You're the last person in it, so it's deleted with its messages. This can't be undone."
              : "It leaves your chats. Its creator, an owner or an admin can add you back."}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Stay</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={leave}>Leave</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
