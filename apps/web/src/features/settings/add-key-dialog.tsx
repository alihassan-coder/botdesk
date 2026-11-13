import { useState } from "react";
import { toast } from "sonner";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group";
import { actions } from "@/data/store";
import type { ModelProvider } from "@/data/types";

/** Which provider the dialog is for; `undefined` adds a new custom (OpenAI-compatible) server. */
interface AddKeyDialogProps {
  provider?: ModelProvider;
  trigger: React.ReactNode;
}

/**
 * Add or replace a provider's API key. The API tries the key against the provider before it's
 * saved, so this shows "Checking…" and then either closes or says why the key didn't work.
 * Once saved, a key is never shown again: only its last 4 characters.
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
  const [showKey, setShowKey] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const valid = isCustom ? label.trim() !== "" && /^https?:\/\/\S+$/.test(baseUrl.trim()) : apiKey.trim() !== "";

  async function save() {
    setChecking(true);
    setError("");
    const input = isCustom ? { apiKey: apiKey.trim(), baseUrl: baseUrl.trim(), label: label.trim() } : { apiKey: apiKey.trim() };
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
        <Field data-invalid={error !== ""}>
          <FieldLabel htmlFor="key-value">{isCustom ? "API key (optional)" : "API key"}</FieldLabel>
          <InputGroup>
            <InputGroupInput id="key-value" type={showKey ? "text" : "password"} autoComplete="off" spellCheck={false}
              value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={isCustom ? "Leave empty if it needs none" : "Paste your key"}
              aria-invalid={error !== ""} />
            <InputGroupAddon align="inline-end">
              <InputGroupButton size="icon-xs" onClick={() => setShowKey((s) => !s)} aria-label={showKey ? "Hide key" : "Show key"}>
                {showKey ? <EyeOff /> : <Eye />}
              </InputGroupButton>
            </InputGroupAddon>
          </InputGroup>
          {error && <FieldError>{error}</FieldError>}
        </Field>
      </FieldGroup>
      <DialogFooter className="mt-6">
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
        <Button type="submit" disabled={!valid || checking}>{checking ? "Checking…" : "Check and save"}</Button>
      </DialogFooter>
    </form>
  );
}
