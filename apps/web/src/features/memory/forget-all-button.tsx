import { toast } from "sonner";
import { Eraser } from "lucide-react";
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

/** "Forget everything" for one bot (owners and admins), behind a confirm: it can't be undone. */
export function ForgetAllButton({ bot, disabled = false }: { bot: Bot; disabled?: boolean }) {
  const forgetAll = async () => {
    const result = await actions.forgetAllMemories(bot.id);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`${bot.name} forgot everything`);
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled} className="text-destructive hover:text-destructive">
          <Eraser /> Forget everything
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Make {bot.name} forget everything?</AlertDialogTitle>
          <AlertDialogDescription>
            Everything it learned goes, from group chats and from every member&apos;s DM, including memories you can&apos;t see. This can&apos;t be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep memories</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={forgetAll}>Forget everything</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
