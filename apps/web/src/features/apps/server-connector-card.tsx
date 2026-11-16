import { ConnectorLogo } from "@/components/connector-logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AccountConnection, ServerConnector } from "@/data/types";
import { GOOGLE_SETUP_GUIDE_URL } from "@/lib/connections";
import { ToolList } from "./tool-list";

/** One of the server's connectors on Connect apps (API mode), with its state and Connect. */
export function ServerConnectorCard({
  connector: c,
  accounts,
  onConnect,
}: {
  connector: ServerConnector;
  /** The visible accounts on this connector, revoked ones left out. */
  accounts: AccountConnection[];
  onConnect: () => void;
}) {
  const notSetUp = c.authType !== null && c.setup === "not-configured";
  const badge =
    c.authType === null ? "Built in"
    : notSetUp ? "Not set up"
    : accounts.some((a) => a.status === "needs_reconnect") ? "Needs reconnect"
    : accounts.length > 0 ? "Connected"
    : null;

  return (
    <article className="flex flex-col gap-3 rounded-2xl border bg-card p-4" aria-label={c.name}>
      <div className="flex items-center gap-3">
        <ConnectorLogo connectorId={c.id} name={c.name} decorative />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{c.name}</p>
          <p className="text-xs text-muted-foreground">Version {c.version}</p>
        </div>
        {badge && <Badge variant={badge === "Needs reconnect" ? "destructive" : badge === "Connected" ? "default" : "secondary"}>{badge}</Badge>}
        {c.authType !== null && (
          <Button size="sm" variant={accounts.length > 0 ? "outline" : "default"} disabled={notSetUp} onClick={onConnect} aria-label={`Connect ${c.name}`}>
            Connect
          </Button>
        )}
      </div>
      <p className="text-sm text-muted-foreground">{c.description}</p>
      {notSetUp && (
        <p className="text-sm text-muted-foreground">
          Not set up on this server.{" "}
          <a className="font-medium text-foreground underline underline-offset-4" href={GOOGLE_SETUP_GUIDE_URL} target="_blank" rel="noreferrer">
            How to set it up
          </a>
        </p>
      )}
      {c.tools.length > 0 && <ToolList tools={c.tools.map((t) => ({ name: t.name, label: t.title, risk: t.risk }))} />}
    </article>
  );
}
