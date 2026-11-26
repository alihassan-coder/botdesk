import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { KeyRound, Plus } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TimeAgo } from "@/components/time-ago";
import { actions, useAuthStatus, useCurrentUser, useMemoryKey, useOrg } from "@/data/store";
import type { MemoryKey, MemoryKeyProvider } from "@/data/types";
import { memoryKeyProviderName } from "@/lib/memory-key";
import { maskedKey } from "@/lib/models";
import { MemoryKeyForm } from "./memory-key-form";
import { ProviderIcon } from "./provider-icon";

/**
 * Settings → Memory's key: the OpenAI or Gemini key the organization's memory uses (remembering and
 * recalling, never replies), and (owners and admins) Add key or Change, which opens the form below
 * it, and Remove. Members see the same, read-only.
 */
export function MemoryKeyCard() {
  const load = useMemoryKey();
  const canManage = useCurrentUser().role !== "member";
  const authStatus = useAuthStatus();
  const orgId = useOrg().id;
  const [changing, setChanging] = useState(false);
  const changeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (authStatus === "signed-in") void actions.loadMemoryKey();
  }, [authStatus, orgId]);

  // Back to Change (Add key once removed) when the form closes or the key goes, so keyboard focus isn't lost.
  const close = () => {
    flushSync(() => setChanging(false));
    changeButton.current?.focus();
  };

  if (!load.current) {
    return load.status === "error" ? (
      <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-4 text-sm">
        Couldn&apos;t load the memory key.
        <Button size="sm" variant="outline" onClick={() => void actions.loadMemoryKey()}>Try again</Button>
      </div>
    ) : (
      <Skeleton className="h-20 rounded-2xl" aria-label="Loading the memory key" />
    );
  }

  const { provider } = load.current;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start gap-3 rounded-2xl border p-4">
        {provider ? (
          <ProviderIcon kind={provider} />
        ) : (
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-muted text-muted-foreground" aria-hidden>
            <KeyRound className="size-4" />
          </span>
        )}
        <Current memoryKey={load.current} />
        {canManage && !changing && (
          <div className="flex gap-2">
            <Button ref={changeButton} size="sm" variant={provider ? "outline" : "default"} onClick={() => setChanging(true)}>
              {provider ? "Change" : <><Plus /> Add key</>}
            </Button>
            {provider && <RemoveButton provider={provider} onRemoved={() => changeButton.current?.focus()} />}
          </div>
        )}
      </div>
      {changing && <MemoryKeyForm current={load.current} onDone={close} />}
      {!canManage && <p className="text-sm text-muted-foreground">Only owners and admins can change the memory key.</p>}
    </div>
  );
}

function Current({ memoryKey }: { memoryKey: MemoryKey }) {
  if (!memoryKey.provider) {
    return (
      <div className="min-w-0 flex-1 basis-40">
        <p className="font-medium">No memory key</p>
        <p className="text-sm text-pretty text-muted-foreground">Memory uses this server&apos;s own key, if it has one.</p>
      </div>
    );
  }
  return (
    <div className="min-w-0 flex-1 basis-40">
      <p className="font-medium">{memoryKeyProviderName(memoryKey.provider)}</p>
      <p className="text-xs text-muted-foreground">
        Key {maskedKey(memoryKey.keyHint)}
        {memoryKey.checkedAt && <> · checked <TimeAgo iso={memoryKey.checkedAt} /></>}
      </p>
    </div>
  );
}

function RemoveButton({ provider, onRemoved }: { provider: MemoryKeyProvider; onRemoved: () => void }) {
  const remove = async () => {
    const result = await actions.removeMemoryKey();
    if (!result.ok) return void toast.error(result.error);
    toast.success("Memory key removed");
    onRemoved();
  };
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive">Remove</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove the memory key?</AlertDialogTitle>
          <AlertDialogDescription>
            Bots go back to this server&apos;s own key for memory, if it has one; without it they stop remembering.
            What they remembered stays, and is found again with another {memoryKeyProviderName(provider)} key.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={remove}>Remove</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
