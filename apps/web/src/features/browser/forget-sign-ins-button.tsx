import { toast } from "sonner";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { actions } from "@/data/store";
import type { Bot } from "@/data/types";

/** Forget sign-ins: closes the bot's browser and deletes its profile, after asking. */
export function ForgetSignInsButton({ bot }: { bot: Bot }) {
  const forget = async () => {
    const result = await actions.forgetSignIns(bot.id);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`${bot.name} is signed out everywhere`);
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive">Forget sign-ins</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Forget {bot.name}&apos;s sign-ins?</AlertDialogTitle>
          <AlertDialogDescription>
            Every site {bot.name} is signed in to will ask it to sign in again. Its browser closes now.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep them</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={forget}>Forget sign-ins</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
