"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { actions, useConnections, useConnectors } from "@/data/store";
import type { Connector } from "@/data/types";
import { RISK } from "@/features/approvals/risk";
import { PageHeader } from "@/features/shell/page-header";
import { ConnectDialog } from "./connect-dialog";
import { ConnectorIcon } from "./connector-icon";

/** /apps — what your bots can reach: connected accounts, apps you can add, and what's coming. */
export function AppsScreen() {
  const connectors = useConnectors();
  const connections = useConnections();
  const [connecting, setConnecting] = useState<Connector | null>(null);

  const available = connectors.filter((c) => c.available);
  const comingSoon = connectors.filter((c) => !c.available);

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Connect apps" />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-4xl flex-col gap-10 p-4 md:p-8">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Connect apps</h2>
            <p className="mt-1 text-sm text-muted-foreground">Give your bots access to your tools. Every action has a risk level, and risky ones wait for approval.</p>
          </div>

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

          <section aria-label="Available">
            <h3 className="mb-3 text-sm font-semibold">Available</h3>
            <div className="grid gap-3 md:grid-cols-2">
              {available.map((c) => (
                <article key={c.id} className="flex flex-col gap-3 rounded-2xl border bg-card p-4">
                  <div className="flex items-center gap-3">
                    <ConnectorIcon category={c.category} />
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{c.name}</p>
                      <p className="text-xs text-muted-foreground">by {c.publisher}</p>
                    </div>
                    <Button size="sm" onClick={() => setConnecting(c)} aria-label={`Connect ${c.name}`}>Connect</Button>
                  </div>
                  <p className="text-sm text-muted-foreground">{c.description}</p>
                  {c.tools.length > 0 && <ToolList connector={c} />}
                </article>
              ))}
            </div>
          </section>

          <section aria-label="Coming soon">
            <h3 className="mb-3 text-sm font-semibold">Coming soon</h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {comingSoon.map((c) => (
                <article key={c.id} className="flex items-center gap-3 rounded-2xl border border-dashed p-4 text-muted-foreground">
                  <ConnectorIcon category={c.category} className="opacity-60" />
                  <div className="min-w-0">
                    <p className="font-medium text-foreground/80">{c.name}</p>
                    <p className="truncate text-xs">{c.description}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      </div>
      <ConnectDialog connector={connecting} onClose={() => setConnecting(null)} />
    </div>
  );
}

/** What bots can do with this app, and how risky each action is. */
function ToolList({ connector }: { connector: Connector }) {
  return (
    <Collapsible className="group/tools">
      <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground">
        <ChevronRight className="size-3.5 transition-transform group-data-[state=open]/tools:rotate-90" />
        What bots can do ({connector.tools.length})
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-2 flex flex-col divide-y rounded-xl border text-sm">
          {connector.tools.map((tool) => {
            const risk = RISK[tool.risk];
            return (
              <li key={tool.name} className="flex items-center gap-2 px-3 py-2">
                <span className="flex-1">{tool.description}</span>
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <risk.icon className="size-3.5" /> {risk.label}
                </span>
              </li>
            );
          })}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}
