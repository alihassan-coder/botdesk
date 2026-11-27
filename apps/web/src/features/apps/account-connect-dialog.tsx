import { useState } from "react";
import { TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConnectorLogo } from "@/components/connector-logo";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { actions, useBots, useCurrentUser } from "@/data/store";
import type { ConnectionOwner, ServerConnector } from "@/data/types";
import { accessLabel } from "@/lib/connections";

/**
 * Connect an account on the API: whose it is (you, a bot, the organization), then sign in with
 * the provider (OAuth, the whole tab goes there) or paste an API key. After signing in the tab
 * comes back to `returnTo`, by default the page the dialog was opened on.
 */
export function AccountConnectDialog({ connector, onClose, returnTo }: { connector: ServerConnector | null; onClose: () => void; returnTo?: string }) {
  return (
    <Dialog open={connector !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>{connector && <ConnectForm key={connector.id} connector={connector} onClose={onClose} returnTo={returnTo} />}</DialogContent>
    </Dialog>
  );
}

function ConnectForm({ connector: c, onClose, returnTo }: { connector: ServerConnector; onClose: () => void; returnTo?: string }) {
  const isAdmin = useCurrentUser().role !== "member";
  const bots = useBots();
  const [ownerKind, setOwnerKind] = useState<ConnectionOwner["kind"]>("member");
  const [botId, setBotId] = useState(bots[0]?.id ?? "");
  const [access, setAccess] = useState(c.defaultAccess ?? c.accessLevels.at(-1) ?? "");
  const [label, setLabel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isKey = c.authType === "api_key";

  async function submit() {
    const owner: ConnectionOwner = ownerKind === "bot" ? { kind: "bot", botId } : { kind: ownerKind };
    setBusy(true);
    setError("");
    const result = isKey
      ? await actions.connectApiKey(c.id, owner, label.trim(), apiKey.trim())
      : await actions.startOAuth(c.id, owner, c.accessLevels.length > 0 ? access : undefined, returnTo);
    setBusy(false); // after OAuth the tab is leaving; nothing else to do
    if (!result.ok) return setError(result.error);
    if (isKey) {
      toast.success(`${c.name} connected`);
      onClose();
    }
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
        <ConnectorLogo connectorId={c.id} name={c.name} decorative />
        <DialogTitle>Connect {c.name}</DialogTitle>
        <DialogDescription>
          {isKey ? "The key is kept encrypted on the server and never shown again." : `You'll sign in with ${c.name}'s provider, then come back here.`}
        </DialogDescription>
      </DialogHeader>

      <FieldSet>
        <FieldLegend variant="label">Whose account is it?</FieldLegend>
        <RadioGroup value={ownerKind} onValueChange={(v) => setOwnerKind(v as ConnectionOwner["kind"])}>
          <OwnerOption value="member" label="Just me" hint="Used only in your own chats with a bot." />
          <OwnerOption value="bot" label="A bot" hint="The bot's own account, used in all its chats." disabled={bots.length === 0} />
          {isAdmin && <OwnerOption value="org" label="The organization" hint="Shared: any bot it's turned on for can use it." />}
        </RadioGroup>
        {ownerKind === "bot" && (
          <Select value={botId} onValueChange={setBotId}>
            <SelectTrigger aria-label="Which bot" className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              {bots.map((b) => <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
      </FieldSet>

      {!isKey && c.accessLevels.length > 1 && (
        <FieldSet>
          <FieldLegend variant="label">Access</FieldLegend>
          <RadioGroup value={access} onValueChange={setAccess}>
            {c.accessLevels.map((level) => <OwnerOption key={level} value={level} label={accessLabel(level)} />)}
          </RadioGroup>
          <FieldDescription>Risky actions still wait for approval, whatever the access.</FieldDescription>
        </FieldSet>
      )}

      {isKey && (
        <>
          {c.id === "demo" && (
            <Alert>
              <TriangleAlert />
              <AlertDescription>The Demo key is sent to a public echo service (postman-echo.com). Use a made-up key, never a real one.</AlertDescription>
            </Alert>
          )}
          <Field>
            <FieldLabel htmlFor="connect-label">Account name</FieldLabel>
            <Input id="connect-label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder={c.name} />
          </Field>
          <Field>
            <FieldLabel htmlFor="connect-key">API key</FieldLabel>
            <Input id="connect-key" type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} required />
          </Field>
        </>
      )}

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
        <Button type="submit" disabled={busy || (isKey && !apiKey.trim()) || (ownerKind === "bot" && !botId)}>
          {isKey ? "Connect" : `Continue to ${c.name}`}
        </Button>
      </DialogFooter>
    </form>
  );
}

function OwnerOption({ value, label, hint, disabled }: { value: string; label: string; hint?: string; disabled?: boolean }) {
  const id = `connect-${value}`;
  return (
    <div className="flex items-start gap-2.5">
      <RadioGroupItem id={id} value={value} disabled={disabled} className="mt-0.5" />
      <label htmlFor={id} className="text-sm">
        <span className="font-medium">{label}</span>
        {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
      </label>
    </div>
  );
}
