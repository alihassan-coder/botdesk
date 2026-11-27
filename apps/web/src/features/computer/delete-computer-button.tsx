import { toast } from "sonner";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { actions } from "@/data/store";
import type { Bot } from "@/data/types";

/** Delete computer: deletes the bot's cloud computer with everything on its disk, after asking. */
export function DeleteComputerButton({ bot, disabled }: { bot: Bot; disabled?: boolean }) {
  const remove = async () => {
    const result = await actions.deleteComputer(bot.id);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`${bot.name}'s computer is deleted`);
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive" disabled={disabled}>Delete computer</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {bot.name}&apos;s computer?</AlertDialogTitle>
          <AlertDialogDescription>
            Everything on its disk is lost: files on the computer, what it installed, its work in progress. {bot.name}&apos;s Files stay.
            The next start makes a new, empty computer.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={remove}>Delete computer</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
