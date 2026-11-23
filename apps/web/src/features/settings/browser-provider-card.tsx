import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Cloud, Globe } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TimeAgo } from "@/components/time-ago";
import { actions, useAuthStatus, useBrowserProvider, useCurrentUser, useOrg } from "@/data/store";
import type { BrowserProvider } from "@/data/types";
import { browserProviderName } from "@/lib/browser-providers";
import { maskedKey } from "@/lib/models";
import { BrowserProviderForm } from "./browser-provider-form";

/**
 * Settings → Computers' Browser: where bots' browsers run now (Local, Steel, Browserbase or
 * Kernel), and (owners and admins) Change, which opens the form below it. Members see the same, read-only.
 */
export function BrowserProviderCard() {
  const load = useBrowserProvider();
  const canManage = useCurrentUser().role !== "member";
  const authStatus = useAuthStatus();
  const orgId = useOrg().id;
  const [changing, setChanging] = useState(false);
  const changeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (authStatus === "signed-in") void actions.loadBrowserProvider();
  }, [authStatus, orgId]);

  // Back to Change once the form closes, so keyboard focus isn't lost with it.
  const close = () => {
    flushSync(() => setChanging(false));
    changeButton.current?.focus();
  };

  if (!load.current) {
    return load.status === "error" ? (
      <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-4 text-sm">
        Couldn&apos;t load where browsers run.
        <Button size="sm" variant="outline" onClick={() => void actions.loadBrowserProvider()}>Try again</Button>
      </div>
    ) : (
      <Skeleton className="h-24 rounded-2xl" aria-label="Loading the browser provider" />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start gap-3 rounded-2xl border p-4">
        <span className="grid size-9 shrink-0 place-items-center rounded-[10px] bg-muted text-muted-foreground">
          {load.current.provider === "local" ? <Globe className="size-4.5" aria-hidden /> : <Cloud className="size-4.5" aria-hidden />}
        </span>
        <Current choice={load.current} canManage={canManage} />
        {canManage && !changing && (
          <Button ref={changeButton} size="sm" variant="outline" onClick={() => setChanging(true)}>Change</Button>
        )}
      </div>
      {changing && <BrowserProviderForm current={load.current} onDone={close} />}
      <p className="text-sm text-muted-foreground">Each bot has its own browser. Watch it and take over in the bot&apos;s Computer tab.</p>
      {!canManage && <p className="text-sm text-muted-foreground">Only owners and admins can change where browsers run.</p>}
    </div>
  );
}

function Current({ choice, canManage }: { choice: BrowserProvider; canManage: boolean }) {
  if (choice.provider !== "local") {
    return (
      <div className="min-w-0 flex-1">
        <p className="font-medium">{browserProviderName(choice.provider)}</p>
        <p className="text-xs text-muted-foreground">
          Key {maskedKey(choice.keyHint)}
          {choice.checkedAt && <> · checked <TimeAgo iso={choice.checkedAt} /></>}
        </p>
        {choice.projectId && <p className="truncate font-mono text-xs text-muted-foreground">Project {choice.projectId}</p>}
      </div>
    );
  }
  return (
    <div className="min-w-0 flex-1">
      <p className="flex flex-wrap items-center gap-2 font-medium">
        Local {!choice.localAvailable && <Badge variant="destructive">Off on this server</Badge>}
      </p>
      <p className="text-sm text-pretty text-muted-foreground">
        {choice.localAvailable
          ? "On this BotDesk server."
          : `This server doesn't run browsers itself, so bots can't browse yet. ${canManage ? "Choose" : "An owner or admin can choose"} a cloud browser provider.`}
      </p>
    </div>
  );
}
