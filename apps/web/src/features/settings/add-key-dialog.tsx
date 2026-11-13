import { useState } from "react";
import { toast } from "sonner";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group";
import { actions } from "@/data/store";
import type { ModelProvider } from "@/data/types";
import { maskedKey } from "@/lib/models";

/** Which provider the dialog is for; `undefined` adds a new custom (OpenAI-compatible) server. */
interface AddKeyDialogProps {
  provider?: ModelProvider;
  trigger: React.ReactNode;
}

/**
 * Add or replace a provider's API key. The API tries the key against the provider before it's
 * saved, so this shows "Checking…" and then either closes or says why the key didn't work.
 * Once saved, a key is never shown again: only its last 4 characters.
 *
 * Editing a custom server: an empty key field keeps the saved key, but only while the base URL
 * stays the same. The API never sends a saved key to a new address, so a changed URL needs the
 * key again, or "This server needs no key".
 */
export function AddKeyDialog({ provider, trigger }: AddKeyDialogProps) {
  const [open, setOpen] = useState(false);
  const isCustom = !provider || provider.kind === "custom";
  const title = !provider ? "Add a custom server" : provider.connected && provider.source === "org" ? `Replace the ${provider.name} key` : `Add a ${provider.name} key`;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {isCustom ? "Any server that speaks OpenAI's API: Ollama, LM Studio, vLLM." : provider.hint}{" "}
            Keys are encrypted and never shown again in full.
          </DialogDescription>
        </DialogHeader>
        {/* Mounted only while open, so it starts empty each time. */}
        {open && <KeyForm provider={provider} isCustom={isCustom} onDone={() => setOpen(false)} />}
      </DialogContent>
    </Dialog>
  );
}

function KeyForm({ provider, isCustom, onDone }: { provider?: ModelProvider; isCustom: boolean; onDone: () => void }) {
  const [label, setLabel] = useState(provider?.kind === "custom" ? provider.name : "");
  const [baseUrl, setBaseUrl] = useState(provider?.baseUrl ?? "");
  const [apiKey, setApiKey] = useState("");
  const [noKey, setNoKey] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  // A custom server being edited that has a saved key: blank keeps it, unless the URL changes.
  const hasSavedKey = provider?.kind === "custom" && Boolean(provider.keyHint);
  const urlChanged = hasSavedKey && sameUrl(baseUrl) !== sameUrl(provider?.baseUrl ?? "");
  const needsKeyAgain = urlChanged && !noKey && apiKey.trim() === "";
  const valid = isCustom
    ? label.trim() !== "" && /^https?:\/\/\S+$/.test(baseUrl.trim()) && !needsKeyAgain
    : apiKey.trim() !== "";

  async function save() {
    setChecking(true);
    setError("");
    const key = noKey ? "" : apiKey.trim();
    const input = isCustom
      ? { apiKey: key, baseUrl: baseUrl.trim(), label: label.trim(), ...(noKey ? { noKey: true } : {}) }
      : { apiKey: key };
    const result = await actions.saveProviderKey(provider?.id ?? "custom", input);
    setChecking(false);
    if (!result.ok) return setError(result.error);
    toast.success(`${isCustom ? label.trim() : provider?.name} is connected`);
    onDone();
  }

  return (
    <form noValidate onSubmit={(e) => { e.preventDefault(); if (valid && !checking) void save(); }}>
      <FieldGroup>
        {isCustom && (
          <>
            <Field>
              <FieldLabel htmlFor="key-label">Name</FieldLabel>
              <Input id="key-label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Ollama on my laptop" />
            </Field>
            <Field>
              <FieldLabel htmlFor="key-url">Base URL</FieldLabel>
              <Input id="key-url" inputMode="url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://localhost:11434/v1" />
              <FieldDescription>The address that ends in /v1. Hosted BotDesk can&apos;t reach private networks.</FieldDescription>
            </Field>
          </>
        )}
        <Field data-invalid={error !== "" || needsKeyAgain} data-disabled={noKey || undefined}>
          <FieldLabel htmlFor="key-value">{isCustom ? "API key (optional)" : "API key"}</FieldLabel>
          <InputGroup>
            <InputGroupInput id="key-value" type={showKey ? "text" : "password"} autoComplete="off" spellCheck={false}
              value={noKey ? "" : apiKey} onChange={(e) => setApiKey(e.target.value)} disabled={noKey}
              placeholder={keyPlaceholder(isCustom, hasSavedKey, urlChanged)}
              aria-invalid={error !== "" || needsKeyAgain} aria-describedby={hasSavedKey ? "key-value-help" : undefined} />
            <InputGroupAddon align="inline-end">
              <InputGroupButton size="icon-xs" onClick={() => setShowKey((s) => !s)} aria-label={showKey ? "Hide key" : "Show key"}>
                {showKey ? <EyeOff /> : <Eye />}
              </InputGroupButton>
            </InputGroupAddon>
          </InputGroup>
          {hasSavedKey && !noKey && (
            <FieldDescription id="key-value-help">
              {urlChanged
                ? "You changed the URL, so paste the key again. A saved key is never sent to a new address."
                : `Leave blank to keep the current key (${maskedKey(provider?.keyHint)}). Changing the URL needs the key again.`}
            </FieldDescription>
          )}
          {error && <FieldError>{error}</FieldError>}
        </Field>
        {hasSavedKey && (
          <Field orientation="horizontal">
            <Checkbox id="key-none" checked={noKey} onCheckedChange={(checked) => setNoKey(checked === true)} />
            <FieldLabel htmlFor="key-none" className="font-normal">This server needs no key (remove the saved one)</FieldLabel>
          </Field>
        )}
      </FieldGroup>
      <DialogFooter className="mt-6">
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
        <Button type="submit" disabled={!valid || checking}>{checking ? "Checking…" : "Check and save"}</Button>
      </DialogFooter>
    </form>
  );
}

/** Compare base URLs the way the API does: trimmed, without a trailing slash. */
function sameUrl(url: string) {
  return url.trim().replace(/\/+$/, "");
}

function keyPlaceholder(isCustom: boolean, hasSavedKey: boolean, urlChanged: boolean) {
  if (!isCustom) return "Paste your key";
  if (hasSavedKey) return urlChanged ? "Paste the key for the new URL" : "Leave blank to keep the current key";
  return "Leave empty if it needs none";
}
