import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { actions, useAuthStatus, useCurrentUser, useIsDemo, useMcpServers, useOrg } from "@/data/store";
import { AddMcpServerDialog } from "./add-mcp-server-dialog";
import { McpServerRow } from "./mcp-server-row";

/**
 * Connect apps: the organization's remote MCP servers (ADR 0012). Everyone sees them; owners and
 * admins add, sign in, review, refresh and remove. Each is a plugin bots get in their Tools tab.
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
          {servers.items.map((server) => <McpServerRow key={server.id} server={server} canManage={isAdmin} />)}
        </ul>
      )}
      <AddMcpServerDialog open={adding} onClose={() => setAdding(false)} />
    </section>
  );
}
