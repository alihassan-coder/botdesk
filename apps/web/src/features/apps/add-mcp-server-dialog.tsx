import { useState } from "react";
import Link from "next/link";
import { ListChecks, TriangleAlert } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { actions, useMcpServers } from "@/data/store";
import { waitingLabel } from "@/lib/mcp-review";

/**
 * Owners and admins: add a remote MCP server. The API connects and lists its tools before
 * saving, so a wrong address or key fails here. The key is optional and never shown again.
 * A server that wants a sign-in (it answers 401, or "Uses sign-in" is ticked) sends the tab to
 * its sign-in page; a client ID is only needed when the server can't register BotDesk itself.
 * Step 2 leads to Review tools: no tool is offered to a bot before that (ADR 0012 §4).
 */
export function AddMcpServerDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [addedId, setAddedId] = useState<string | null>(null);
  const close = () => {
    setAddedId(null);
    onClose();
  };
  return (
    <Dialog open={open} onOpenChange={(next) => !next && close()}>
      <DialogContent>
        {open && (addedId ? <ReviewNext serverId={addedId} onClose={close} /> : <AddForm onAdded={setAddedId} onClose={close} />)}
      </DialogContent>
    </Dialog>
  );
}

/** Step 2: the server is saved; its tools wait for the review. */
function ReviewNext({ serverId, onClose }: { serverId: string; onClose: () => void }) {
  const server = useMcpServers().items.find((s) => s.id === serverId);
  const waiting = server ? waitingLabel(server.tools) : null;
  return (
    <div className="flex flex-col gap-5">
      <DialogHeader>
        <DialogTitle>{server?.name ?? "Server"} added</DialogTitle>
        <DialogDescription>
          {waiting ? `${waiting}. ` : ""}No bot gets its tools until you&apos;ve read what each one says and chosen which to offer. Then turn the server on in a bot&apos;s Tools.
        </DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>Later</Button>
        <Button asChild>
          <Link href={`/apps/mcp/${serverId}`} onClick={onClose}><ListChecks /> Review tools</Link>
        </Button>
      </DialogFooter>
    </div>
  );
}

function AddForm({ onAdded, onClose }: { onAdded: (serverId: string) => void; onClose: () => void }) {
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
    if (result.signingIn) return onClose(); // the tab is leaving for the sign-in page
    onAdded(result.serverId);
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
        <DialogDescription>BotDesk connects to it now and lists its tools. You review them next; bots get them only once you have, and the server is on in their Tools.</DialogDescription>
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
        <AlertDescription>Every tool from this server starts by asking before acting (you can change each one&apos;s risk in the review), and what it returns is treated as outside text: after it, risky actions always wait for approval.</AlertDescription>
      </Alert>

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        <Button type="submit" disabled={busy || !name.trim() || !url.trim() || halfKey || secretWithoutId}>{busy ? "Connecting…" : signIn ? "Add and sign in" : "Add server"}</Button>
      </DialogFooter>
    </form>
  );
}
