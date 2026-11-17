import { useState } from "react";
import { TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { actions } from "@/data/store";

/**
 * Owners and admins: add a remote MCP server. The API connects and lists its tools before
 * saving, so a wrong address or key fails here. The key is optional and never shown again.
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
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const halfKey = Boolean(header.trim()) !== Boolean(key.trim());

  async function submit() {
    setBusy(true);
    setError("");
    const withKey = header.trim() && key.trim() ? { apiKeyHeader: header.trim(), apiKeyValue: key.trim() } : {};
    const result = await actions.addMcpServer({ name: name.trim(), url: url.trim(), ...withKey });
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

      <FieldSet>
        <FieldLegend variant="label">API key (optional)</FieldLegend>
        <div className="grid gap-3 sm:grid-cols-[2fr_3fr]">
          <Input aria-label="Header name" value={header} onChange={(e) => setHeader(e.target.value)} placeholder="Authorization" autoComplete="off" />
          <Input aria-label="Header value" type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="Bearer sk-…" autoComplete="off" />
        </div>
        <FieldDescription>Sent in this header on every request. Kept encrypted on the server and never shown again.</FieldDescription>
      </FieldSet>

      <Alert>
        <TriangleAlert />
        <AlertDescription>Every tool from this server asks before acting, and what it returns is treated as outside text: after it, risky actions always wait for approval.</AlertDescription>
      </Alert>

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        <Button type="submit" disabled={busy || !name.trim() || !url.trim() || halfKey}>{busy ? "Connecting…" : "Add server"}</Button>
      </DialogFooter>
    </form>
  );
}
