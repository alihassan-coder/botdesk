import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { FieldDescription, FieldGroup, FieldLegend, FieldSet } from "@/components/ui/field";
import { RadioGroup } from "@/components/ui/radio-group";
import { actions, useMemoryStatus } from "@/data/store";
import type { MemoryKey, MemoryKeyProvider } from "@/data/types";
import { MEMORY_KEY_PROVIDERS, memoryKeyProblem, memoryKeyProviderName } from "@/lib/memory-key";
import { ProviderOption } from "./provider-option";
import { SecretField } from "./secret-field";

/**
 * Add or change the organization's memory key (owners and admins). The API tries the key with the
 * provider first, so this says "Checking…" and then either closes or shows why under the key.
 */
export function MemoryKeyForm({ current, onDone }: { current: MemoryKey; onDone: () => void }) {
  const memoryOn = useMemoryStatus()?.enabled ?? false;
  const [provider, setProvider] = useState<MemoryKeyProvider>(current.provider ?? "openai");
  const [apiKey, setApiKey] = useState("");
  const [tried, setTried] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const problem = memoryKeyProblem(provider, apiKey);
  // Memories are kept per provider. Without a key of its own, memory that's on uses the server's OpenAI key.
  const inUse = current.provider ?? (memoryOn ? "openai" : undefined);

  async function save() {
    setTried(true);
    if (problem) return;
    setChecking(true);
    setError("");
    const result = await actions.saveMemoryKey(provider, apiKey);
    setChecking(false);
    if (!result.ok) return setError(result.error);
    toast.success(`Memory now uses your ${memoryKeyProviderName(provider)} key`);
    onDone();
  }

  return (
    <form noValidate aria-label={current.provider ? "Change the memory key" : "Add a memory key"} className="flex flex-col gap-6 rounded-2xl border p-4"
      onSubmit={(e) => { e.preventDefault(); if (!checking) void save(); }}>
      <FieldSet>
        <FieldLegend variant="label">Provider</FieldLegend>
        <RadioGroup value={provider} onValueChange={(value) => { setProvider(value as MemoryKeyProvider); setApiKey(""); setError(""); setTried(false); }}>
          {MEMORY_KEY_PROVIDERS.map((p) => (
            <ProviderOption key={p.id} group="memory" value={p.id} label={p.name} hint={p.hint} autoFocus={provider === p.id} />
          ))}
        </RadioGroup>
        <FieldDescription>BotDesk is free; memory&apos;s model calls are billed by the provider you choose.</FieldDescription>
      </FieldSet>

      <FieldGroup>
        <SecretField id="memory-key" label="API key" value={apiKey} keepsSaved={false}
          problem={error || (tried ? problem : undefined)} onChange={(value) => { setApiKey(value); setError(""); }} />
      </FieldGroup>

      {inUse && inUse !== provider && (
        <p className="text-sm text-muted-foreground">
          Memories are kept per provider: what bots remembered with {memoryKeyProviderName(inUse)} is found again only if you switch back.
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
        <Button type="submit" disabled={checking}>{checking ? "Checking…" : "Check and save"}</Button>
      </div>
    </form>
  );
}
