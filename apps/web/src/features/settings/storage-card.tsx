import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Cloud, HardDrive } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TimeAgo } from "@/components/time-ago";
import { actions, useAuthStatus, useCurrentUser, useFileStorage, useOrg } from "@/data/store";
import type { FileStorage } from "@/data/types";
import { maskedKey } from "@/lib/models";
import { describeBucket } from "@/lib/storage";
import { StorageForm } from "./storage-form";

/**
 * Settings → Computers' Storage: where the organization's files are kept now, and (owners and
 * admins) Change, which opens the form below it. Members see the same, read-only.
 */
export function StorageCard() {
  const load = useFileStorage();
  const canManage = useCurrentUser().role !== "member";
  const authStatus = useAuthStatus();
  const orgId = useOrg().id;
  const [changing, setChanging] = useState(false);
  const changeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (authStatus === "signed-in") void actions.loadStorage();
  }, [authStatus, orgId]);

  // Back to Change once the form closes, so keyboard focus isn't lost with it.
  const close = () => {
    flushSync(() => setChanging(false));
    changeButton.current?.focus();
  };

  if (!load.current) {
    return load.status === "error" ? (
      <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-4 text-sm">
        Couldn&apos;t load where files are kept.
        <Button size="sm" variant="outline" onClick={() => void actions.loadStorage()}>Try again</Button>
      </div>
    ) : (
      <Skeleton className="h-24 rounded-2xl" aria-label="Loading storage" />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start gap-3 rounded-2xl border p-4">
        <span className="grid size-9 shrink-0 place-items-center rounded-[10px] bg-muted text-muted-foreground">
          {load.current.provider === "s3" ? <Cloud className="size-4.5" aria-hidden /> : <HardDrive className="size-4.5" aria-hidden />}
        </span>
        <Current storage={load.current} canManage={canManage} />
        {canManage && !changing && (
          <Button ref={changeButton} size="sm" variant="outline" onClick={() => setChanging(true)}>Change</Button>
        )}
      </div>
      {changing && <StorageForm current={load.current} onDone={close} />}
      <p className="text-sm text-muted-foreground">
        Each bot gets a folder named after it inside <Path>botdesk/</Path>, plus <Path>_shared</Path> for files every bot can read.
      </p>
      {!canManage && <p className="text-sm text-muted-foreground">Only owners and admins can change where files go.</p>}
    </div>
  );
}

function Current({ storage, canManage }: { storage: FileStorage; canManage: boolean }) {
  if (storage.provider === "s3" && storage.s3) {
    return (
      <div className="min-w-0 flex-1">
        <p className="font-medium">S3-compatible</p>
        <p className="truncate font-mono text-xs text-muted-foreground" title={describeBucket(storage.s3)}>{describeBucket(storage.s3)}</p>
        <p className="text-xs text-muted-foreground">
          Key {maskedKey(storage.s3.accessKeyHint)}
          {storage.checkedAt && <> · checked <TimeAgo iso={storage.checkedAt} /></>}
        </p>
      </div>
    );
  }
  return (
    <div className="min-w-0 flex-1">
      <p className="flex flex-wrap items-center gap-2 font-medium">
        Local {!storage.localAvailable && <Badge variant="destructive">Off on this server</Badge>}
      </p>
      <p className="text-sm text-pretty text-muted-foreground">
        {storage.localAvailable
          ? "On this BotDesk server."
          : `This server doesn't keep files itself, so bots can't save any yet. ${canManage ? "Choose" : "An owner or admin can choose"} an S3-compatible bucket.`}
      </p>
    </div>
  );
}

function Path({ children }: { children: React.ReactNode }) {
  return <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs text-foreground">{children}</code>;
}
