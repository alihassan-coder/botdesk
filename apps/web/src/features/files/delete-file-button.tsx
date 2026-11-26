import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { actions } from "@/data/store";
import type { BotFile } from "@/data/types";
import type { FileFolder } from "@/lib/files";

/** Delete a file, after asking. Any member may; no bot can read it afterwards. */
export function DeleteFileButton({ folder, file }: { folder: FileFolder; file: BotFile }) {
  const remove = async () => {
    const result = await actions.deleteFile(folder.key, file.id);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`Deleted ${file.path}`);
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="text-muted-foreground hover:text-destructive" aria-label={`Delete ${file.path}`}>
          <Trash2 />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="break-all">Delete {file.path}?</AlertDialogTitle>
          <AlertDialogDescription>
            {file.available
              ? `It's removed from ${folder.phrase} and from your storage. This can't be undone.`
              : "It leaves this list. The copy in the storage you used before stays there."}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={remove}>Delete</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
