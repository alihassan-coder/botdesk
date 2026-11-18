import { useEffect, useState } from "react";
import Link from "next/link";
import { ConnectorLogo } from "@/components/connector-logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { actions, useAccountConnections, useBotTools, useCurrentUser } from "@/data/store";
import type { AccountConnection, Bot, BotToolPlugin, BotTrigger } from "@/data/types";
import { ToolList } from "@/features/apps/tool-list";
import { bindableConnections } from "@/lib/connections";

/**
 * A bot's Tools tab: which plugins it may use, and which connected account each works through.
 * A bot only has the tools of the plugins switched on here. Your own account works only in your
 * own chats with the bot; a bot's or the organization's works in every chat.
 */
export function BotTools({ bot }: { bot: Bot }) {
  const tools = useBotTools(bot.id);
  const accounts = useAccountConnections().items;
  const user = useCurrentUser();
  const me = user.id;
  const isAdmin = user.role !== "member";
  const [error, setError] = useState("");

  useEffect(() => {
    void actions.loadBotTools(bot.id);
  }, [bot.id]);

  if (!tools || (tools.status === "loading" && tools.plugins.length === 0)) return <Skeleton className="h-24 rounded-xl" />;
  if (tools.status === "error" && tools.plugins.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-6 text-sm text-muted-foreground">
        <p>Couldn&apos;t load {bot.name}&apos;s tools.</p>
        <Button variant="outline" size="sm" onClick={() => void actions.loadBotTools(bot.id)}>Try again</Button>
      </div>
    );
  }

  async function change(plugin: BotToolPlugin, patch: Partial<Pick<BotToolPlugin, "enabled" | "connectionId">>) {
    setError("");
    const result = await actions.setBotTools(bot.id, [
      { pluginId: plugin.pluginId, enabled: patch.enabled ?? plugin.enabled, connectionId: patch.connectionId !== undefined ? patch.connectionId : plugin.connectionId },
    ]);
    if (!result.ok) setError(result.error);
  }

  async function switchTrigger(plugin: BotToolPlugin, trigger: BotTrigger, enabled: boolean) {
    setError("");
    const result = await actions.setBotTrigger(bot.id, plugin.pluginId, trigger.name, enabled);
    if (!result.ok) setError(result.error);
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">{bot.name} can use only the apps switched on here. Risky actions still wait for approval.</p>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {tools.plugins.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">This server has no plugins switched on.</p>}
      {tools.plugins.map((plugin) => (
        <PluginCard
          key={plugin.pluginId}
          plugin={plugin}
          choices={plugin.authType ? bindableConnections(accounts, plugin.pluginId, bot.id, me) : []}
          onChange={(patch) => void change(plugin, patch)}
          botName={bot.name}
          me={me}
          isAdmin={isAdmin}
          onTrigger={(trigger, enabled) => void switchTrigger(plugin, trigger, enabled)}
        />
      ))}
    </div>
  );
}

function PluginCard({
  plugin: p,
  choices,
  onChange,
  botName,
  me,
  isAdmin,
  onTrigger,
}: {
  plugin: BotToolPlugin;
  choices: AccountConnection[];
  onChange: (patch: Partial<Pick<BotToolPlugin, "enabled" | "connectionId">>) => void;
  botName: string;
  me: string;
  isAdmin: boolean;
  onTrigger: (trigger: BotTrigger, enabled: boolean) => void;
}) {
  // The account in use may be another member's (it isn't offered, but it's still shown).
  const current = p.connectionId && !choices.some((c) => c.id === p.connectionId) ? p.connectionId : null;
  const selectId = `account-${p.pluginId}`;
  // An MCP server with the organization's key or sign-in: switching it binds an org account (owners and admins).
  const locked = Boolean(p.mcp?.orgAccount) && !isAdmin;

  return (
    <article className="flex flex-col gap-3 rounded-xl border p-3" aria-label={p.name}>
      <div className="flex items-start gap-3">
        <ConnectorLogo connectorId={p.pluginId} name={p.name} size="sm" decorative />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{p.name}</p>
          <p className="text-xs text-muted-foreground">{p.description}</p>
        </div>
        {p.mcp && p.mcp.toolsWaiting > 0 && <Badge variant="outline">{p.mcp.toolsWaiting === 1 ? "1 tool to review" : `${p.mcp.toolsWaiting} tools to review`}</Badge>}
        <Switch checked={p.enabled} disabled={locked} onCheckedChange={(enabled) => onChange({ enabled })} aria-label={`Use ${p.name}`} />
      </div>
      {p.mcp && <McpNotes mcp={p.mcp} locked={locked} isAdmin={isAdmin} />}
      {p.authType && (
        <div className="flex flex-col gap-1.5">
          <label htmlFor={selectId} className="text-xs font-medium text-muted-foreground">Account</label>
          <NativeSelect id={selectId} size="sm" className="w-full" value={p.connectionId ?? ""} onChange={(e) => onChange({ connectionId: e.target.value || null })}>
            <NativeSelectOption value="">No account</NativeSelectOption>
            {current && <NativeSelectOption value={current}>Someone else&apos;s account</NativeSelectOption>}
            {choices.map((c) => (
              <NativeSelectOption key={c.id} value={c.id}>
                {c.accountLabel} ({c.ownerKind === "member" ? "yours" : c.ownerKind === "bot" ? "this bot's" : "organization"})
              </NativeSelectOption>
            ))}
          </NativeSelect>
          {choices.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No account connected yet. <Link href="/apps" className="font-medium text-foreground underline underline-offset-4">Connect one</Link>
            </p>
          )}
        </div>
      )}
      {/* Triggers need the app on with an account: their runs read through it. */}
      {p.enabled && p.connectionId && p.triggers?.map((t) => (
        <TriggerRow key={t.name} id={`trigger-${p.pluginId}-${t.name}`} trigger={t} botName={botName} mine={t.subscriberId === me} onChange={(enabled) => onTrigger(t, enabled)} />
      ))}
      {p.tools.length > 0 && <ToolList tools={p.tools.map((t) => ({ name: t.name, label: t.title, risk: t.risk }))} />}
    </article>
  );
}

/** What an MCP server's card adds: tools paused for a review, a sign-in problem, who may switch it. */
function McpNotes({ mcp, locked, isAdmin }: { mcp: NonNullable<BotToolPlugin["mcp"]>; locked: boolean; isAdmin: boolean }) {
  return (
    <>
      {mcp.toolsWaiting > 0 && (
        <p className="text-xs text-muted-foreground">
          {mcp.toolsWaiting === 1 ? "1 tool changed or is new on the server" : `${mcp.toolsWaiting} tools changed or are new on the server`}: bots don&apos;t get {mcp.toolsWaiting === 1 ? "it" : "them"} until {isAdmin ? "you review them" : "an owner or admin reviews them"} in{" "}
          <Link href="/apps" className="font-medium text-foreground underline underline-offset-4">Connect apps</Link>.
        </p>
      )}
      {mcp.problem && <p role="status" className="text-xs text-destructive">{mcp.problem}</p>}
      {locked && <p className="text-xs text-muted-foreground">It uses the organization&apos;s key or sign-in, so only owners and admins switch it on or off.</p>}
    </>
  );
}

/** A plugin's trigger ("React to new email"): when on, each event comes to the DM of whoever switched it on, and the bot reads it there. */
function TriggerRow({ id, trigger: t, botName, mine, onChange }: { id: string; trigger: BotTrigger; botName: string; mine: boolean; onChange: (enabled: boolean) => void }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg bg-muted/50 p-2.5">
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={id} className="text-sm font-medium">{t.title}</label>
        <Switch id={id} checked={t.enabled} onCheckedChange={onChange} aria-label={t.title} />
      </div>
      <p className="text-xs text-muted-foreground">
        {!t.enabled ? t.description
        : mine ? `What it finds comes to your chat with ${botName}, checked about once a minute. Anything risky still asks you first.`
        : "Switched on by another member: what it finds goes to their chat with this bot."}
      </p>
      {t.problem && <p role="status" className="text-xs text-destructive">{t.problem}</p>}
    </div>
  );
}
