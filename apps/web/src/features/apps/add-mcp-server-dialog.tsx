import { useState } from "react";
import { TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { actions } from "@/data/store";

/**
 * Owners and admins: add a remote MCP server. The API connects and lists its tools before
 * saving, so a wrong address or key fails here. The key is optional and never shown again.
 * A server that wants a sign-in (it answers 401, or "Uses sign-in" is ticked) sends the tab to
 * its sign-in page; a client ID is only needed when the server can't register BotDesk itself.
 */
export function AddMcpServerDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>{open && <AddForm onClose={onClose} />}</DialogContent>
    </Dialog>
  );
}

function AddForm({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [header, setHeader] = useState("");
  const [key, setKey] = useState("");
  const [signIn, setSignIn] = useState(false);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const halfKey = !signIn && Boolean(header.trim()) !== Boolean(key.trim());
  const secretWithoutId = signIn && Boolean(clientSecret.trim()) && !clientId.trim();

  async function submit() {
    setBusy(true);
    setError("");
    const withKey = !signIn && header.trim() && key.trim() ? { apiKeyHeader: header.trim(), apiKeyValue: key.trim() } : {};
    const withClient = signIn
      ? { signIn: true, ...(clientId.trim() ? { oauthClientId: clientId.trim() } : {}), ...(clientSecret.trim() ? { oauthClientSecret: clientSecret.trim() } : {}) }
      : {};
    const result = await actions.addMcpServer({ name: name.trim(), url: url.trim(), ...withKey, ...withClient });
    setBusy(false);
    if (!result.ok) return setError(result.error);
    toast.success(`${name.trim()} added. Turn it on for a bot in its Tools.`);
    onClose();
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
      className="flex flex-col gap-5"
    >
      <DialogHeader>
        <DialogTitle>Add MCP server</DialogTitle>
        <DialogDescription>BotDesk connects to it now and lists its tools. Bots get them only when you turn the server on in their Tools.</DialogDescription>
      </DialogHeader>

      <Field>
        <FieldLabel htmlFor="mcp-name">Name</FieldLabel>
        <Input id="mcp-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Issue tracker" maxLength={80} required />
      </Field>
      <Field>
        <FieldLabel htmlFor="mcp-url">Server URL</FieldLabel>
        <Input id="mcp-url" type="url" inputMode="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://mcp.example.com/mcp" required />
        <FieldDescription>Streamable HTTP over https.</FieldDescription>
      </Field>

      <Field orientation="horizontal">
        <Checkbox id="mcp-sign-in" checked={signIn} onCheckedChange={(v) => setSignIn(v === true)} />
        <FieldLabel htmlFor="mcp-sign-in" className="font-normal">Uses sign-in (OAuth)</FieldLabel>
      </Field>

      {signIn ? (
        <FieldSet>
          <FieldLegend variant="label">OAuth client (optional)</FieldLegend>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input aria-label="Client ID" value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder="Client ID" autoComplete="off" />
            <Input aria-label="Client secret" type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} placeholder="Client secret" autoComplete="off" />
          </div>
          <FieldDescription>Leave empty and BotDesk registers itself with the server. Paste one only if the server asks you to create it. The secret is kept encrypted and never shown again.</FieldDescription>
        </FieldSet>
      ) : (
        <FieldSet>
          <FieldLegend variant="label">API key (optional)</FieldLegend>
          <div className="grid gap-3 sm:grid-cols-[2fr_3fr]">
            <Input aria-label="Header name" value={header} onChange={(e) => setHeader(e.target.value)} placeholder="Authorization" autoComplete="off" />
            <Input aria-label="Header value" type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Bearer sk-…" autoComplete="off" />
          </div>
          <FieldDescription>Sent in this header on every request. Kept encrypted on the server and never shown again. A server that asks for a sign-in instead is detected when you add it.</FieldDescription>
        </FieldSet>
      )}

      <Alert>
        <TriangleAlert />
        <AlertDescription>Every tool from this server starts by asking before acting (you can review each one&apos;s risk afterwards), and what it returns is treated as outside text: after it, risky actions always wait for approval.</AlertDescription>
      </Alert>

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        <Button type="submit" disabled={busy || !name.trim() || !url.trim() || halfKey || secretWithoutId}>{busy ? "Connecting…" : signIn ? "Add and sign in" : "Add server"}</Button>
      </DialogFooter>
    </form>
  );
}
