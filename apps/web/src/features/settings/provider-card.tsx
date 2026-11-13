import { useState } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TimeAgo } from "@/components/time-ago";
import { actions } from "@/data/store";
import type { ModelProvider } from "@/data/types";
import { maskedKey } from "@/lib/models";
import { AddKeyDialog } from "./add-key-dialog";
import { ProviderIcon } from "./provider-icon";

/**
 * One model provider in Settings → Models & keys: connected (••••1234, Test / Replace / Remove)
 * or not (Add key). `canManage` is false for members, who only look.
 */
export function ProviderCard({ provider, canManage }: { provider: ModelProvider; canManage: boolean }) {
  const fromServer = provider.source === "env";
  const ownKey = provider.connected && provider.source === "org";

  return (
    <li className="flex flex-col gap-3 rounded-2xl border p-4">
      <div className="flex items-start gap-3">
        <ProviderIcon kind={provider.kind} />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 font-medium">
            {provider.name}
            {provider.status === "invalid" ? <Badge variant="destructive">Key not working</Badge>
              : provider.connected && <Badge variant="secondary">Connected</Badge>}
          </p>
          <p className="text-sm text-muted-foreground">{provider.hint}</p>
        </div>
      </div>
      {provider.connected && (
        <p className="truncate font-mono text-xs text-muted-foreground">
          {fromServer ? "Key set on the server" : provider.baseUrl ?? maskedKey(provider.keyHint)}
          {provider.baseUrl && provider.keyHint && <> · {maskedKey(provider.keyHint)}</>}
          {provider.lastVerifiedAt && <> · checked <TimeAgo iso={provider.lastVerifiedAt} /></>}
        </p>
      )}
      {canManage && (
        <div className="mt-auto flex flex-wrap gap-2">
          {ownKey && <TestButton provider={provider} />}
          <AddKeyDialog provider={provider} trigger={
            <Button size="sm" variant={provider.connected ? "outline" : "default"}>
              {ownKey ? "Replace" : <><Plus /> Add key</>}
            </Button>
          } />
          {ownKey && <RemoveKeyButton provider={provider} />}
        </div>
      )}
    </li>
  );
}

function TestButton({ provider }: { provider: ModelProvider }) {
  const [testing, setTesting] = useState(false);
  const test = async () => {
    setTesting(true);
    const result = await actions.testProviderKey(provider.id);
    setTesting(false);
    if (result.ok) toast.success(`${provider.name}: the key works`);
    else toast.error(result.error);
  };
  return <Button size="sm" variant="outline" disabled={testing} onClick={test}>{testing ? "Testing…" : "Test"}</Button>;
}

function RemoveKeyButton({ provider }: { provider: ModelProvider }) {
  const remove = async () => {
    const result = await actions.removeProviderKey(provider.id);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`Removed the ${provider.name} key`);
  };
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive">Remove</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove the {provider.name} key?</AlertDialogTitle>
          <AlertDialogDescription>
            Bots using {provider.name} models stop replying for real until a key is added again
            (or they use the server&apos;s key, if it has one).
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
