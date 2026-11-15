"use client";

import { useEffect } from "react";
import { Puzzle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { actions, useAuthStatus, useOrg, usePlugins } from "@/data/store";
import { ToolList } from "./tool-list";

/**
 * API only: the plugins the server loaded. They're built in, so every bot can use them with
 * nothing to connect; each tool's risk decides whether the bot asks first.
 */
export function BuiltInPlugins() {
  const plugins = usePlugins();
  const signedIn = useAuthStatus() === "signed-in";
  const orgId = useOrg().id;

  useEffect(() => {
    if (signedIn) void actions.loadPlugins();
  }, [signedIn, orgId]);

  return (
    <section aria-label="Built in">
      <h3 className="mb-3 text-sm font-semibold">Built in</h3>
      {plugins.status === "loading" && plugins.items.length === 0 ? (
        <Skeleton className="h-24 rounded-2xl" />
      ) : plugins.status === "error" ? (
        <div className="flex items-center gap-3 rounded-2xl border border-dashed p-4 text-sm text-muted-foreground">
          <p className="flex-1">Couldn&apos;t load the built-in apps.</p>
          <Button variant="outline" size="sm" onClick={() => void actions.loadPlugins()}>Try again</Button>
        </div>
      ) : plugins.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">This server has no plugins switched on.</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {plugins.items.map((plugin) => (
            <article key={plugin.id} className="flex flex-col gap-3 rounded-2xl border bg-card p-4">
              <div className="flex items-center gap-3">
                <span className="grid size-10 shrink-0 place-items-center rounded-xl border bg-muted/50"><Puzzle className="size-5 text-muted-foreground" /></span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{plugin.name}</p>
                  <p className="text-xs text-muted-foreground">Version {plugin.version}</p>
                </div>
                <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">Built in</span>
              </div>
              <p className="text-sm text-muted-foreground">{plugin.description}</p>
              {plugin.tools.length > 0 && <ToolList tools={plugin.tools.map((t) => ({ name: t.name, label: t.title, risk: t.risk }))} />}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
