import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { actions, useAccountConnections, useAuthStatus, useOrg, useServerConnectors } from "@/data/store";
import type { AccountConnection, ServerConnector } from "@/data/types";
import { AccountConnectDialog } from "./account-connect-dialog";
import { ServerConnectorCard } from "./server-connector-card";
import { YourConnections } from "./your-connections";

/**
 * API only: your connected accounts, then the server's connectors (its plugins). Built-in ones
 * need nothing; the rest connect an account by signing in (OAuth) or with an API key.
 */
export function ServerConnectors() {
  const connectors = useServerConnectors();
  const accounts = useAccountConnections();
  const signedIn = useAuthStatus() === "signed-in";
  const orgId = useOrg().id;
  const [connecting, setConnecting] = useState<ServerConnector | null>(null);

  useEffect(() => {
    if (signedIn) void actions.loadConnections();
  }, [signedIn, orgId]);

  // Revoked accounts stay on the server for the audit log; people don't need to see them.
  const live = useMemo(() => accounts.items.filter((a) => a.status !== "revoked"), [accounts.items]);
  const byConnector = useMemo(() => {
    const map = new Map<string, AccountConnection[]>();
    for (const a of live) map.set(a.connectorId, [...(map.get(a.connectorId) ?? []), a]);
    return map;
  }, [live]);

  if (connectors.status === "loading" && connectors.items.length === 0) return <Skeleton className="h-24 rounded-2xl" />;
  if (connectors.status === "error") {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-dashed p-4 text-sm text-muted-foreground">
        <p className="flex-1">Couldn&apos;t load the apps.</p>
        <Button variant="outline" size="sm" onClick={() => void actions.loadConnections()}>Try again</Button>
      </div>
    );
  }

  return (
    <>
      <YourConnections accounts={live} connectors={connectors.items} />
      <section aria-label="Apps">
        <h3 className="mb-3 text-sm font-semibold">Apps</h3>
        {connectors.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">This server has no plugins switched on.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {connectors.items.map((c) => (
              <ServerConnectorCard key={c.id} connector={c} accounts={byConnector.get(c.id) ?? []} onConnect={() => setConnecting(c)} />
            ))}
          </div>
        )}
      </section>
      <AccountConnectDialog connector={connecting} onClose={() => setConnecting(null)} />
    </>
  );
}
