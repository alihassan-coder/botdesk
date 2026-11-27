import { useState, type ReactNode } from "react";
import { ConnectorLogo } from "@/components/connector-logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useCurrentUser, useIsDemo, useMcpServers } from "@/data/store";
import { catalogueEntryFor, MCP_CATALOGUE, signInLine, type McpCatalogueEntry } from "@/lib/mcp-catalogue";
import { AddMcpServerDialog } from "./add-mcp-server-dialog";

/**
 * Connect apps: the official remote MCP servers (lib/mcp-catalogue.ts), each hosted by its company,
 * and a custom one. Connect (owners and admins, as with Add server) opens Add MCP server filled in
 * for that server; one already added says so. The demo can't add servers, so its Connect is off.
 */
export function OfficialMcpServers() {
  const isDemo = useIsDemo();
  const isAdmin = useCurrentUser().role !== "member";
  const servers = useMcpServers().items;
  // `preset: null` is the custom server: the dialog opens empty.
  const [adding, setAdding] = useState<{ preset: McpCatalogueEntry | null } | null>(null);
  const added = new Set(servers.map((s) => catalogueEntryFor(s.url)?.id));

  const connectButton = (name: string, open: () => void) =>
    isAdmin && (
      <Button size="sm" variant="outline" disabled={isDemo} onClick={open} aria-label={`Connect ${name}`}>Connect</Button>
    );

  return (
    <section aria-label="Official MCP servers">
      <h3 className="text-sm font-semibold">Official MCP servers</h3>
      <p className="mt-1 text-sm text-muted-foreground">Hosted by each company. Connect one and review its tools before bots use them.</p>
      {(isDemo || !isAdmin) && (
        <p className="mt-1 text-sm text-muted-foreground">{isDemo ? "Sign up to connect MCP servers." : "Owners and admins connect these. Ask one for what your bots need."}</p>
      )}
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {MCP_CATALOGUE.map((entry) => (
          <ServerCard
            key={entry.id}
            logoId={entry.id}
            name={entry.name}
            label={`${entry.name} MCP server`}
            byline={`by ${entry.publisher}`}
            description={entry.description}
            signIn={signInLine(entry)}
            action={added.has(entry.id) ? <Badge variant="secondary">Added</Badge> : connectButton(`${entry.name} MCP server`, () => setAdding({ preset: entry }))}
          />
        ))}
        {/* The demo has its own custom server card under Available. */}
        {!isDemo && (
          <ServerCard
            logoId="mcp"
            name="Custom MCP server"
            label="Custom MCP server"
            byline="Any company's, or your own"
            description="Connect any remote MCP server by its URL."
            signIn="With an API key, a sign-in or neither"
            action={connectButton("Custom MCP server", () => setAdding({ preset: null }))}
          />
        )}
      </div>
      <AddMcpServerDialog open={adding !== null} preset={adding?.preset ?? null} onClose={() => setAdding(null)} />
    </section>
  );
}

function ServerCard({ logoId, name, label, byline, description, signIn, action }: {
  logoId: string;
  name: string;
  /** Says "MCP server", so it isn't mixed up with an app of the same name under Apps. */
  label: string;
  byline: string;
  description: string;
  signIn: string;
  action: ReactNode;
}) {
  return (
    <article aria-label={label} className="flex flex-col gap-3 rounded-2xl border bg-card p-4">
      <div className="flex items-center gap-3">
        <ConnectorLogo connectorId={logoId} name={name} decorative />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{name}</p>
          <p className="text-xs text-muted-foreground">{byline}</p>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">{description}</p>
      <div className="mt-auto flex items-center gap-3">
        <p className="min-w-0 flex-1 text-xs text-muted-foreground">{signIn}</p>
        {action}
      </div>
    </article>
  );
}
