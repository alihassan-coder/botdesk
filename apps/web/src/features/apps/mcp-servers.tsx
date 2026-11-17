import { useEffect, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { actions, useAuthStatus, useCurrentUser, useIsDemo, useMcpServers, useOrg } from "@/data/store";
import type { McpServer } from "@/data/types";
import { AddMcpServerDialog } from "./add-mcp-server-dialog";
import { ToolList } from "./tool-list";

/**
 * Connect apps: the organization's remote MCP servers (ADR 0012). Everyone sees them; owners and
 * admins add, refresh and remove. Each is a plugin bots get in their Tools tab.
 */
export function McpServers() {
  const isDemo = useIsDemo();
  const servers = useMcpServers();
  const isAdmin = useCurrentUser().role !== "member";
  const signedIn = useAuthStatus() === "signed-in";
  const orgId = useOrg().id;
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    if (signedIn) void actions.loadMcpServers();
  }, [signedIn, orgId]);

  return (
    <section aria-label="MCP servers">
      <div className="mb-3 flex items-center gap-3">
        <h3 className="flex-1 text-sm font-semibold">MCP servers</h3>
        {isAdmin && !isDemo && (
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
            <Plus /> Add server
          </Button>
        )}
      </div>
      {isDemo ? (
        <p className="text-sm text-muted-foreground">Connect botdesk to its API to add MCP servers: any remote MCP server&apos;s tools become bot tools.</p>
      ) : servers.status === "loading" && servers.items.length === 0 ? (
        <Skeleton className="h-20 rounded-2xl" />
      ) : servers.status === "error" ? (
        <div className="flex items-center gap-3 rounded-2xl border border-dashed p-4 text-sm text-muted-foreground">
          <p className="flex-1">Couldn&apos;t load the MCP servers.</p>
          <Button variant="outline" size="sm" onClick={() => void actions.loadMcpServers()}>Try again</Button>
        </div>
      ) : servers.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {isAdmin ? "No MCP servers yet. Add one to give bots its tools." : "No MCP servers yet. Owners and admins can add them."}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {servers.items.map((server) => <ServerRow key={server.id} server={server} canManage={isAdmin} />)}
        </ul>
      )}
      <AddMcpServerDialog open={adding} onClose={() => setAdding(false)} />
    </section>
  );
}

function ServerRow({ server, canManage }: { server: McpServer; canManage: boolean }) {
  const [refreshing, setRefreshing] = useState(false);
  const unreachable = server.status === "unreachable";

  async function refresh() {
    setRefreshing(true);
    const result = await actions.refreshMcpServer(server.id);
    setRefreshing(false);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`${server.name}'s tools are up to date`);
  }

  return (
    <li className="flex flex-col gap-3 rounded-2xl border bg-card p-4" aria-label={server.name}>
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-medium">{server.name}</p>
          <p className="truncate text-sm text-muted-foreground">
            {server.url} · {server.tools.length === 1 ? "1 tool" : `${server.tools.length} tools`}
            {unreachable && server.statusReason ? ` · ${server.statusReason}` : ""}
          </p>
        </div>
        <Badge variant={unreachable ? "destructive" : "secondary"}>{unreachable ? "Unreachable" : "MCP"}</Badge>
        {canManage && (
          <>
            <Button size="sm" variant="ghost" onClick={() => void refresh()} disabled={refreshing} aria-label={`Refresh ${server.name}`}>
              <RefreshCw className={refreshing ? "animate-spin" : undefined} /> Refresh
            </Button>
            <RemoveButton server={server} />
          </>
        )}
      </div>
      {server.tools.length > 0 && (
        <ToolList tools={server.tools.map((t) => ({ name: t.name, label: t.title ?? t.serverName, risk: "external-send" }))} />
      )}
    </li>
  );
}

function RemoveButton({ server }: { server: McpServer }) {
  const remove = async () => {
    const result = await actions.removeMcpServer(server.id);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`Removed ${server.name}`);
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="sm">Remove</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove {server.name}?</AlertDialogTitle>
          <AlertDialogDescription>Every bot loses its tools straight away, and BotDesk forgets its key. You can add it again later.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={remove}>Remove</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
