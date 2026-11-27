import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { toast } from "sonner";
import { Field, FieldDescription, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group";
import { useOAuthCallbackUrl } from "@/data/store";
import type { McpCatalogueEntry } from "@/lib/mcp-catalogue";

type Setter = (value: string) => void;

/**
 * Sign-in's OAuth client. Optional when the server registers BotDesk itself; required for an
 * official server whose vendor makes you create the app first, with how-to and the redirect URI.
 */
export function OAuthClientFields({ preset, clientId, clientSecret, setClientId, setClientSecret }: {
  preset: McpCatalogueEntry | null;
  clientId: string;
  clientSecret: string;
  setClientId: Setter;
  setClientSecret: Setter;
}) {
  const setup = preset?.signIn.kind === "oauth-client" ? preset.signIn : null;
  return (
    <FieldSet>
      <FieldLegend variant="label">{setup ? "OAuth client" : "OAuth client (optional)"}</FieldLegend>
      {preset && setup && (
        <>
          <FieldDescription>
            {setup.steps} Then paste its client ID and secret here. <a href={preset.docsUrl} target="_blank" rel="noreferrer">{preset.publisher}&apos;s guide</a>
          </FieldDescription>
          <RedirectUri />
        </>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Input aria-label="Client ID" value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder="Client ID" autoComplete="off" required={Boolean(setup)} />
        <Input aria-label="Client secret" type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} placeholder="Client secret" autoComplete="off" required={Boolean(setup)} />
      </div>
      <FieldDescription>
        {setup
          ? "The secret is kept encrypted and never shown again."
          : "Leave empty and BotDesk registers itself with the server. Paste one only if the server asks you to create it. The secret is kept encrypted and never shown again."}
      </FieldDescription>
    </FieldSet>
  );
}

/** What the vendor's console must be given, so its sign-in sends people back to BotDesk. */
function RedirectUri() {
  const uri = useOAuthCallbackUrl();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(uri);
      setCopied(true);
    } catch {
      toast.error("Couldn't copy. Select the address and copy it yourself.");
    }
  };
  return (
    <Field>
      <FieldLabel htmlFor="mcp-redirect-uri">Redirect URI</FieldLabel>
      <InputGroup>
        <InputGroupInput id="mcp-redirect-uri" readOnly value={uri} onFocus={(e) => e.currentTarget.select()} className="font-mono text-xs" />
        <InputGroupAddon align="inline-end">
          <InputGroupButton onClick={() => void copy()} aria-label={copied ? "Copied redirect URI" : "Copy redirect URI"}>
            {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy"}
          </InputGroupButton>
        </InputGroupAddon>
      </InputGroup>
    </Field>
  );
}

/** A header key: optional for a custom server; an official one says which header, its form and where to get it. */
export function ApiKeyFields({ preset, header, value, setHeader, setValue }: {
  preset: McpCatalogueEntry | null;
  header: string;
  value: string;
  setHeader: Setter;
  setValue: Setter;
}) {
  const key = preset?.signIn.kind === "key" ? preset.signIn : null;
  return (
    <FieldSet>
      <FieldLegend variant="label">{key ? "API key" : "API key (optional)"}</FieldLegend>
      <div className="grid gap-3 sm:grid-cols-[2fr_3fr]">
        <Input aria-label="Header name" value={header} onChange={(e) => setHeader(e.target.value)} placeholder="Authorization" autoComplete="off" required={Boolean(key)} />
        <Input aria-label="Header value" type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder={key?.valuePlaceholder ?? "Bearer sk-…"} autoComplete="off" required={Boolean(key)} />
      </div>
      {preset && key && (
        <FieldDescription>
          {key.where} <a href={preset.docsUrl} target="_blank" rel="noreferrer">{preset.publisher}&apos;s guide</a>
        </FieldDescription>
      )}
      <FieldDescription>
        Sent in this header on every request. Kept encrypted on the server and never shown again.
        {key ? "" : " A server that asks for a sign-in instead is detected when you add it."}
      </FieldDescription>
    </FieldSet>
  );
}
