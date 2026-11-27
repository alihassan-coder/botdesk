import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Monitor, Plus } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TimeAgo } from "@/components/time-ago";
import { actions, useAuthStatus, useComputerProvider, useCurrentUser, useIsDemo, useOrg } from "@/data/store";
import type { ComputerProvider } from "@/data/types";
import { ORGO_KEYS_URL } from "@/lib/computer";
import { maskedKey } from "@/lib/models";
import { CloudComputerForm } from "./cloud-computer-form";

/**
 * Settings → Computers' Cloud computer (ADR 0020): the organization's own Orgo key, which gives each
 * bot set to a cloud computer a Linux computer of its own. Owners and admins add, replace or remove the
 * key; members see the same, read-only. The demo says it needs an account.
 */
export function CloudComputerCard() {
  const load = useComputerProvider();
  const canManage = useCurrentUser().role !== "member";
  const isDemo = useIsDemo();
  const authStatus = useAuthStatus();
  const orgId = useOrg().id;
  const [changing, setChanging] = useState(false);
  const changeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (authStatus === "signed-in") void actions.loadComputerProvider();
  }, [authStatus, orgId]);

  // Back to the button once the form closes or the key goes, so keyboard focus isn't lost with it.
  const close = () => {
    flushSync(() => setChanging(false));
    changeButton.current?.focus();
  };

  if (!load.current) {
    return load.status === "error" ? (
      <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-4 text-sm">
        Couldn&apos;t load the cloud computer key.
        <Button size="sm" variant="outline" onClick={() => void actions.loadComputerProvider()}>Try again</Button>
      </div>
    ) : (
      <Skeleton className="h-24 rounded-2xl" aria-label="Loading the cloud computer key" />
    );
  }

  const hasKey = load.current.provider !== undefined;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start gap-3 rounded-2xl border p-4">
        <span className="grid size-9 shrink-0 place-items-center rounded-[10px] bg-muted text-muted-foreground">
          <Monitor className="size-4.5" aria-hidden />
        </span>
        <Current provider={load.current} />
        {canManage && !isDemo && !changing && (
          <div className="flex gap-2">
            <Button ref={changeButton} size="sm" variant={hasKey ? "outline" : "default"} onClick={() => setChanging(true)}>
              {hasKey ? "Replace key" : <><Plus /> Add Orgo key</>}
            </Button>
            {hasKey && <RemoveButton onRemoved={() => changeButton.current?.focus()} />}
          </div>
        )}
      </div>
      {changing && <CloudComputerForm replacing={hasKey} onDone={close} />}
      <p className="text-sm text-pretty text-muted-foreground">
        A bot set to Cloud computer gets a Linux computer of its own, with a shell and a screen you can watch and take over.
        Bring your own Orgo key: Orgo bills your account, about $0.055 an hour while a computer runs, and BotDesk stops it after
        20 idle minutes.{" "}
        <a href={ORGO_KEYS_URL} target="_blank" rel="noreferrer" className="font-medium text-brand hover:underline">Create an Orgo key</a>
      </p>
      {isDemo ? (
        <p className="text-sm text-muted-foreground">Cloud computers need an account: sign up, then add your Orgo key here.</p>
      ) : (
        !canManage && <p className="text-sm text-muted-foreground">Only owners and admins can change the cloud computer key.</p>
      )}
    </div>
  );
}

function Current({ provider }: { provider: ComputerProvider }) {
  if (!provider.provider) {
    return (
      <div className="min-w-0 flex-1 basis-40">
        <p className="font-medium">No cloud computers yet</p>
        <p className="text-sm text-pretty text-muted-foreground">Bots work with Files and a browser.</p>
      </div>
    );
  }
  return (
    <div className="min-w-0 flex-1 basis-40">
      <p className="flex flex-wrap items-center gap-2 font-medium">
        Orgo {provider.status === "key_refused" && <Badge variant="destructive">Key refused</Badge>}
      </p>
      {provider.status === "key_refused" ? (
        <p className="text-sm text-pretty text-destructive">Key {maskedKey(provider.keyHint)} refused: replace it.</p>
      ) : (
        <p className="text-xs text-muted-foreground">
          Key {maskedKey(provider.keyHint)}
          {provider.checkedAt && <> · checked <TimeAgo iso={provider.checkedAt} /></>}
        </p>
      )}
    </div>
  );
}

function RemoveButton({ onRemoved }: { onRemoved: () => void }) {
  const remove = async () => {
    const result = await actions.removeComputerProvider();
    if (!result.ok) return void toast.error(result.error);
    toast.success("Orgo key removed");
    onRemoved();
  };
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive">Remove</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove the Orgo key?</AlertDialogTitle>
          <AlertDialogDescription>
            Every bot&apos;s cloud computer is stopped, and bots set to Cloud computer can&apos;t start one until a key is added again.
            Their disks stay in your Orgo account.
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
