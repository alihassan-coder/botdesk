"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { actions, useConnections, useConnectors, useIsDemo } from "@/data/store";
import type { Connector } from "@/data/types";
import { PageHeader } from "@/features/shell/page-header";
import { BuiltInPlugins } from "./built-in-plugins";
import { ConnectDialog } from "./connect-dialog";
import { ConnectorIcon } from "./connector-icon";
import { ToolList } from "./tool-list";

/**
 * /apps — what your bots can reach. The demo connects its mock apps. On the API, the server's
 * plugins are built in, and the app catalogue waits for real connections (OAuth, MCP), so it's
 * shown as coming soon with Connect off.
 */
export function AppsScreen() {
  const isDemo = useIsDemo();
  const connectors = useConnectors();
  const [connecting, setConnecting] = useState<Connector | null>(null);

  const available = connectors.filter((c) => c.available);
  const comingSoon = isDemo ? connectors.filter((c) => !c.available) : connectors;

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Connect apps" />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-4xl flex-col gap-10 p-4 md:p-8">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Connect apps</h2>
            <p className="mt-1 text-sm text-muted-foreground">Give your bots access to your tools. Every action has a risk level, and risky ones wait for approval.</p>
          </div>

          {isDemo ? (
            <>
              <Connections connectors={connectors} />
              <section aria-label="Available">
                <h3 className="mb-3 text-sm font-semibold">Available</h3>
                <div className="grid gap-3 md:grid-cols-2">
                  {available.map((c) => <ConnectorCard key={c.id} connector={c} onConnect={() => setConnecting(c)} />)}
                </div>
              </section>
            </>
          ) : (
            <BuiltInPlugins />
          )}

          <section aria-label="Coming soon">
            <h3 className="mb-3 text-sm font-semibold">Coming soon</h3>
            {!isDemo && <p className="mb-3 text-sm text-muted-foreground">Connecting your own accounts arrives with app connections.</p>}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {comingSoon.map((c) => (
                <article key={c.id} className="flex items-center gap-3 rounded-2xl border border-dashed p-4 text-muted-foreground">
                  <ConnectorIcon category={c.category} className="opacity-60" />
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-foreground/80">{c.name}</p>
                    <p className="truncate text-xs">{c.description}</p>
                  </div>
                  {c.available && <Button size="sm" variant="outline" disabled aria-label={`Connect ${c.name}`}>Connect</Button>}
                </article>
              ))}
            </div>
          </section>
        </div>
      </div>
      {isDemo && <ConnectDialog connector={connecting} onClose={() => setConnecting(null)} />}
    </div>
  );
}

/** MOCK: the demo's connected accounts. */
function Connections({ connectors }: { connectors: Connector[] }) {
  const connections = useConnections();
  return (
    <section aria-label="Connected">
      <h3 className="mb-3 text-sm font-semibold">Connected</h3>
      {connections.length === 0 && <p className="text-sm text-muted-foreground">Nothing connected yet.</p>}
      <ul className="flex flex-col gap-2">
        {connections.map((conn) => {
          const connector = connectors.find((c) => c.id === conn.connectorId);
          if (!connector) return null;
          return (
            <li key={conn.id} className="flex items-center gap-3 rounded-2xl border bg-card p-4">
              <ConnectorIcon category={connector.category} />
              <div className="min-w-0 flex-1">
                <p className="font-medium">{connector.name}</p>
                <p className="truncate text-sm text-muted-foreground">{conn.account}</p>
              </div>
              <span className="hidden rounded-full bg-success/12 px-2 py-0.5 text-xs font-medium text-success sm:inline">Connected</span>
              <Button variant="ghost" size="sm" onClick={() => actions.disconnectApp(conn.id)}>Disconnect</Button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function ConnectorCard({ connector: c, onConnect }: { connector: Connector; onConnect: () => void }) {
  return (
    <article className="flex flex-col gap-3 rounded-2xl border bg-card p-4">
      <div className="flex items-center gap-3">
        <ConnectorIcon category={c.category} />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{c.name}</p>
          <p className="text-xs text-muted-foreground">by {c.publisher}</p>
        </div>
        <Button size="sm" onClick={onConnect} aria-label={`Connect ${c.name}`}>Connect</Button>
      </div>
      <p className="text-sm text-muted-foreground">{c.description}</p>
      {c.tools.length > 0 && <ToolList tools={c.tools.map((t) => ({ name: t.name, label: t.description, risk: t.risk }))} />}
    </article>
  );
}
