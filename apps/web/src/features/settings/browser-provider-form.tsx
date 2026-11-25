import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup } from "@/components/ui/radio-group";
import { actions } from "@/data/store";
import type { BrowserProvider, BrowserProviderId } from "@/data/types";
import { CLOUD_BROWSERS, browserKeyProblem } from "@/lib/browser-providers";
import { ProviderOption } from "./provider-option";
import { SecretField } from "./secret-field";

/**
 * Change where the organization's bots' browsers run (owners and admins). For a cloud provider the
 * API starts and stops a browser there with the key first, which can take a few seconds, so this
 * says "Checking…" and then either closes or shows the API's reason.
 */
export function BrowserProviderForm({ current, onDone }: { current: BrowserProvider; onDone: () => void }) {
  const [provider, setProvider] = useState<BrowserProviderId>(current.localAvailable || current.provider !== "local" ? current.provider : "steel");
  const [apiKey, setApiKey] = useState("");
  const [projectId, setProjectId] = useState(current.projectId);
  const [tried, setTried] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const cloud = CLOUD_BROWSERS.find((p) => p.id === provider);
  const problem = browserKeyProblem(provider, apiKey, current);

  async function save() {
    setTried(true);
    if (problem) return;
    setChecking(true);
    setError("");
    const result = await actions.saveBrowserProvider(provider === "local" ? { provider } : { provider, apiKey, projectId });
    setChecking(false);
    if (!result.ok) return setError(result.error);
    toast.success(cloud ? `Bots' browsers now run at ${cloud.name}` : "Bots' browsers now run on this BotDesk server");
    onDone();
  }

  return (
    <form noValidate aria-label="Change browser provider" className="flex flex-col gap-6 rounded-2xl border p-4"
      onSubmit={(e) => { e.preventDefault(); if (!checking) void save(); }}>
      <FieldSet>
        <FieldLegend variant="label">Run browsers</FieldLegend>
        <RadioGroup value={provider} onValueChange={(value) => { setProvider(value as BrowserProviderId); setApiKey(""); setError(""); setTried(false); }}>
          <ProviderOption group="browser" value="local" label="Local" disabled={!current.localAvailable} autoFocus={provider === "local"}
            hint={current.localAvailable ? "On this BotDesk server. Each open browser uses about 300–500 MB of its memory." : "Turned off on this server."} />
          {CLOUD_BROWSERS.map((p) => (
            <ProviderOption key={p.id} group="browser" value={p.id} label={p.name} hint={p.hint} autoFocus={provider === p.id} />
          ))}
        </RadioGroup>
        <FieldDescription>BotDesk is free; browser time is billed by the provider you choose. Local is free.</FieldDescription>
      </FieldSet>

      {cloud && (
        <FieldGroup>
          <a href={cloud.pricingUrl} target="_blank" rel="noreferrer" className="w-fit text-sm underline underline-offset-4 hover:text-primary">
            {cloud.name} pricing
          </a>
          <SecretField id="browser-key" label="API key" value={apiKey} problem={tried ? problem : undefined}
            onChange={(value) => { setApiKey(value); setError(""); }} keepsSaved={current.provider === provider && current.keyHint !== undefined} />
          {provider === "browserbase" && (
            <Field>
              <FieldLabel htmlFor="browser-project">Project ID (optional)</FieldLabel>
              <Input id="browser-project" value={projectId} onChange={(e) => { setProjectId(e.target.value); setError(""); }}
                autoComplete="off" autoCapitalize="none" spellCheck={false} aria-describedby="browser-project-hint" />
              <FieldDescription id="browser-project-hint">Leave empty to use the key&apos;s own project.</FieldDescription>
            </Field>
          )}
        </FieldGroup>
      )}

      <p className="text-sm text-muted-foreground">Each bot keeps its own sign-ins at the provider. Changing provider means signing in again.</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
        <Button type="submit" disabled={checking}>{checking ? "Checking…" : "Check and save"}</Button>
      </div>
    </form>
  );
}
