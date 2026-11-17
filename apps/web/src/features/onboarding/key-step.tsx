import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useModelProviders, useModelsLoading } from "@/data/store";
import { AddKeyDialog } from "@/features/settings/add-key-dialog";
import { ProviderIcon } from "@/features/settings/provider-icon";
import { StepFrame } from "./step-frame";

/**
 * Step 2: an AI provider key, with the same dialog as Settings → Models & keys (the API checks
 * the key before saving it). Without one, bots still answer, with a stand-in reply.
 */
export function KeyStep({ onNext }: { onNext: () => void }) {
  const providers = useModelProviders().filter((p) => p.kind !== "custom");
  const loading = useModelsLoading();
  const anyConnected = providers.some((p) => p.connected);

  return (
    <StepFrame
      title="Add an AI key"
      description="Bots think with a model from a provider you already use. Paste one key now; you can add more in Settings → Models & keys."
      onSkip={onNext}
      skipLabel="Skip — bots will use a stand-in reply"
      action={<Button onClick={onNext} disabled={!anyConnected}>Continue</Button>}
    >
      {loading && providers.length === 0 ? (
        <Skeleton className="h-48 rounded-2xl" />
      ) : providers.length === 0 ? (
        <p className="rounded-2xl border border-dashed p-4 text-sm text-muted-foreground">
          The providers didn&apos;t load. You can add a key later in Settings → Models & keys.
        </p>
      ) : (
        <ul className="divide-y rounded-2xl border" aria-label="Providers">
          {providers.map((p) => (
            <li key={p.id} className="flex items-center gap-3 p-3">
              <ProviderIcon kind={p.kind} />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{p.name}</p>
                <p className="truncate text-xs text-muted-foreground">{p.hint}</p>
              </div>
              {p.connected ? (
                <Badge variant="secondary">Connected</Badge>
              ) : (
                <AddKeyDialog provider={p} trigger={
                  <Button size="sm" variant="outline" aria-label={`Add key for ${p.name}`}><Plus /> Add key</Button>
                } />
              )}
            </li>
          ))}
        </ul>
      )}
    </StepFrame>
  );
}
