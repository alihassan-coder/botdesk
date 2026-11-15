import { useState } from "react";
import Link from "next/link";
import { Pencil, Play, Trash2 } from "lucide-react";
import { toast } from "sonner";
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
import type { Routine } from "@/data/types";

/** Run now, Edit and Delete: for the routine's creator, owners and admins. */
export function RoutineActions({ routine }: { routine: Routine }) {
  const [running, setRunning] = useState(false);

  async function runNow() {
    setRunning(true);
    const result = await actions.runRoutineNow(routine.id);
    setRunning(false);
    if (result.ok) toast.success(`“${routine.name}” is running. The reply will be in your chat with the bot.`);
    else toast.error(result.error);
  }

  async function remove() {
    const result = await actions.deleteRoutine(routine.id);
    if (result.ok) toast.success(`“${routine.name}” deleted.`);
    else toast.error(result.error);
  }

  return (
    <div className="flex flex-wrap gap-1">
      <Button variant="outline" size="sm" onClick={() => void runNow()} disabled={running || !routine.botId}>
        <Play /> Run now
      </Button>
      <Button asChild variant="ghost" size="sm">
        <Link href={`/routines/${routine.id}/edit`} aria-label={`Edit ${routine.name}`}>
          <Pencil /> Edit
        </Link>
      </Button>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="ghost" size="sm" aria-label={`Delete ${routine.name}`}>
            <Trash2 /> Delete
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete “{routine.name}”?</AlertDialogTitle>
            <AlertDialogDescription>It stops running. Replies it already got stay in the chat.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => void remove()}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
