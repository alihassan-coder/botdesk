import { useState } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { actions } from "@/data/store";

const PROVIDERS = ["Anthropic", "OpenAI", "Google", "xAI", "Mistral", "DeepSeek", "OpenRouter", "Custom (OpenAI-compatible)"];

/** "Add key": a model provider's API key, for you or for the whole org. The key is shown masked afterwards. */
export function AddKeyDialog() {
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState(PROVIDERS[0]);
  const [key, setKey] = useState("");
  const [owner, setOwner] = useState<"user" | "org">("user");
  const [baseUrl, setBaseUrl] = useState("");
  const isCustom = provider.startsWith("Custom");
  const valid = key.trim().length >= 8 && (!isCustom || /^https?:\/\//.test(baseUrl));

  function save() {
    actions.addCredential({ provider, key: key.trim(), owner, label: owner === "org" ? "Org key" : "My key", baseUrl: isCustom ? baseUrl : undefined });
    toast.success(`${provider} key added`);
    setKey("");
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus /> Add key</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add an API key</DialogTitle>
          <DialogDescription>Keys are encrypted and never shown again in full.</DialogDescription>
        </DialogHeader>
        <form onSubmit={(e) => { e.preventDefault(); if (valid) save(); }}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="key-provider">Provider</FieldLabel>
              <Select value={provider} onValueChange={setProvider}>
                <SelectTrigger id="key-provider" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{PROVIDERS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            {isCustom && (
              <Field>
                <FieldLabel htmlFor="key-url">Base URL</FieldLabel>
                <Input id="key-url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://gpu-box:8000/v1" />
              </Field>
            )}
            <Field>
              <FieldLabel htmlFor="key-value">API key</FieldLabel>
              <Input id="key-value" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder="sk-…" />
            </Field>
            <Field>
              <FieldLabel>Who uses it</FieldLabel>
              <ToggleGroup type="single" variant="outline" value={owner} onValueChange={(v) => v && setOwner(v as "user" | "org")} className="w-full">
                <ToggleGroupItem value="user" className="flex-1">Just me</ToggleGroupItem>
                <ToggleGroupItem value="org" className="flex-1">Whole org</ToggleGroupItem>
              </ToggleGroup>
              <FieldDescription>Org keys are paid by the org and usable by everyone&apos;s bots.</FieldDescription>
            </Field>
          </FieldGroup>
          <DialogFooter className="mt-6">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={!valid}>Add key</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
