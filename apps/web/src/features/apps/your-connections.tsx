import { useCallback } from "react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { ConnectorLogo } from "@/components/connector-logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { actions, useBots, useCurrentUser, useMcpServers } from "@/data/store";
import type { AccountConnection, McpServer, ServerConnector } from "@/data/types";
import { ownerLabel, ownerOf } from "@/lib/connections";

/** API only: the connected accounts you may see, with Reconnect (when broken) and Disconnect. */
export function YourConnections({ accounts, connectors }: { accounts: AccountConnection[]; connectors: ServerConnector[] }) {
  const me = useCurrentUser();
  const bots = useBots();
  const mcpServers = useMcpServers().items;
  const botName = useCallback((botId: string) => bots.find((b) => b.id === botId)?.name, [bots]);

  return (
    <section aria-label="Your connections">
      <h3 className="mb-3 text-sm font-semibold">Your connections</h3>
      {accounts.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing connected yet. Connect an app below to give bots access to it.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {accounts.map((account) => {
            const connector = connectors.find((c) => c.id === account.connectorId);
            // An MCP server's sign-in is named after the server (it isn't a built-in connector).
            const mcp = mcpServers.find((m) => m.pluginId === account.connectorId);
            const name = connector?.name ?? (mcp ? `${mcp.name} (MCP)` : account.connectorId);
            const broken = account.status === "needs_reconnect";
            return (
              <li key={account.id} className="flex flex-wrap items-center gap-3 rounded-2xl border bg-card p-4">
                <ConnectorLogo connectorId={account.connectorId} name={name} decorative />
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{name} <span className="font-normal text-muted-foreground">· {account.accountLabel}</span></p>
                  <p className="truncate text-sm text-muted-foreground">
                    {ownerLabel(account, me.id, botName)}
                    {broken && account.statusReason ? ` · ${account.statusReason}` : ""}
                  </p>
                </div>
                <Badge variant={broken ? "destructive" : "secondary"}>{broken ? "Needs reconnect" : "Connected"}</Badge>
                {broken && account.authType === "oauth2" && (
                  <Button size="sm" onClick={() => void reconnect(account, mcp)}>Reconnect</Button>
                )}
                <DisconnectButton name={name} account={account} />
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

async function reconnect(account: AccountConnection, mcp: McpServer | undefined) {
  // An MCP server signs in again through its own route (its client and scopes live on the server).
  const result = mcp ? await actions.signInMcpServer(mcp.id) : await actions.startOAuth(account.connectorId, ownerOf(account));
  if (!result.ok) toast.error(result.error);
}

function DisconnectButton({ name, account }: { name: string; account: AccountConnection }) {
  const disconnect = async () => {
    const result = await actions.disconnectConnection(account.id);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`Disconnected ${account.accountLabel}`);
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="sm">Disconnect</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Disconnect {account.accountLabel}?</AlertDialogTitle>
          <AlertDialogDescription>
            Bots stop using this {name} account straight away, and BotDesk forgets its sign-in. You can connect it again later.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={disconnect}>Disconnect</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
