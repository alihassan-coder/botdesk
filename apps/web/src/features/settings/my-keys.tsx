import { useEffect } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TimeAgo } from "@/components/time-ago";
import { actions, useAuthStatus, useMyKeys, useOrg } from "@/data/store";
import type { ModelProvider } from "@/data/types";
import { maskedKey } from "@/lib/models";
import { AddKeyDialog } from "./add-key-dialog";
import { ProviderIcon } from "./provider-icon";

/**
 * My keys: your own API key per built-in provider in this organization. Any member adds them.
 * Only you see them (by their last 4 characters), and only the runs you start (your messages,
 * your routines and triggers) use them, before the organization's key.
 */
export function MyKeys() {
  const keys = useMyKeys();
  const orgId = useOrg().id;
  const authStatus = useAuthStatus();

  useEffect(() => {
    if (authStatus === "signed-in") void actions.loadMyKeys();
  }, [authStatus, orgId]);

  if (!keys) {
    return <div className="grid gap-3 @xl:grid-cols-2" aria-busy="true">{[0, 1].map((i) => <Skeleton key={i} className="h-28 rounded-2xl" />)}</div>;
  }
  return (
    <ul className="grid gap-3 @xl:grid-cols-2">
      {keys.map((key) => <MyKeyCard key={key.id} provider={key} />)}
    </ul>
  );
}

function MyKeyCard({ provider }: { provider: ModelProvider }) {
  return (
    <li className="flex flex-col gap-3 rounded-2xl border p-4">
      <div className="flex items-start gap-3">
        <ProviderIcon kind={provider.kind} />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 font-medium">
            {provider.name}
            {provider.status === "invalid" ? <Badge variant="destructive">Key not working</Badge>
              : provider.connected && <Badge variant="secondary">Your key</Badge>}
          </p>
          <p className="text-sm text-pretty break-words text-muted-foreground">{provider.hint}</p>
        </div>
      </div>
      {provider.connected && (
        <p className="truncate font-mono text-xs text-muted-foreground">
          {maskedKey(provider.keyHint)}
          {provider.lastVerifiedAt && <> · checked <TimeAgo iso={provider.lastVerifiedAt} /></>}
        </p>
      )}
      <div className="mt-auto flex flex-wrap gap-2">
        <AddKeyDialog mine provider={provider} trigger={
          <Button size="sm" variant={provider.connected ? "outline" : "default"}>
            {provider.connected ? "Replace" : <><Plus /> Add your key</>}
          </Button>
        } />
        {provider.connected && <RemoveMyKeyButton provider={provider} />}
      </div>
    </li>
  );
}

function RemoveMyKeyButton({ provider }: { provider: ModelProvider }) {
  const remove = async () => {
    const result = await actions.removeMyKey(provider.id);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`Removed your ${provider.name} key`);
  };
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive">Remove</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove your {provider.name} key?</AlertDialogTitle>
          <AlertDialogDescription>
            Your requests go back to the organization&apos;s {provider.name} key, or the server&apos;s, if there is one.
            Otherwise bots on {provider.name} models give you a stand-in reply.
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
