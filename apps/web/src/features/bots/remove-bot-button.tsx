import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
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
import { Button } from "@/components/ui/button";
import { actions } from "@/data/store";
import type { Bot } from "@/data/types";

/** "Remove" in a bot's details (owners and admins). Its chat goes with it, so we head home. */
export function RemoveBotButton({ bot }: { bot: Bot }) {
  const router = useRouter();

  const remove = async () => {
    const result = await actions.removeBot(bot.id);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`Removed ${bot.name}`);
    router.push("/");
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive"><Trash2 /> Remove</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove {bot.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            It stops working for your team straight away, and its chat, routines and waiting approvals go with it. This can&apos;t be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep {bot.name}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={remove}>Remove</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
