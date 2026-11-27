import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { FieldGroup } from "@/components/ui/field";
import { actions } from "@/data/store";
import { ORGO_KEYS_URL } from "@/lib/computer";
import { SecretField } from "./secret-field";

/** The API takes keys of at least this many characters. */
const MIN_KEY = 8;

function keyProblem(apiKey: string): string | undefined {
  const key = apiKey.trim();
  if (!key) return "Paste your Orgo API key.";
  return key.length < MIN_KEY ? "That key looks too short. Paste the whole key." : undefined;
}

/**
 * Add or replace the organization's Orgo key (owners and admins). The API checks it with Orgo first,
 * so this says "Checking…" and then either closes or shows Orgo's reason under the key.
 */
export function CloudComputerForm({ replacing, onDone }: { replacing: boolean; onDone: () => void }) {
  const [apiKey, setApiKey] = useState("");
  const [tried, setTried] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const problem = keyProblem(apiKey);

  async function save() {
    setTried(true);
    if (problem) return;
    setChecking(true);
    setError("");
    const result = await actions.saveComputerProvider(apiKey);
    setChecking(false);
    if (!result.ok) return setError(result.error);
    toast.success("Bots can now have cloud computers at Orgo");
    onDone();
  }

  return (
    <form noValidate aria-label={replacing ? "Replace the Orgo key" : "Add an Orgo key"} className="flex flex-col gap-6 rounded-2xl border p-4"
      onSubmit={(e) => { e.preventDefault(); if (!checking) void save(); }}>
      <FieldGroup>
        <SecretField id="orgo-key" label="Orgo API key" value={apiKey} keepsSaved={false}
          problem={error || (tried ? problem : undefined)} onChange={(value) => { setApiKey(value); setError(""); }} />
      </FieldGroup>
      <p className="text-sm text-pretty text-muted-foreground">
        Make one at Orgo under API keys; it starts with <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs text-foreground">sk_live_</code>.{" "}
        <a href={ORGO_KEYS_URL} target="_blank" rel="noreferrer" className="underline underline-offset-4 hover:text-primary">Open Orgo&apos;s API keys</a>
      </p>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
        <Button type="submit" disabled={checking}>{checking ? "Checking…" : "Check and save"}</Button>
      </div>
    </form>
  );
}
