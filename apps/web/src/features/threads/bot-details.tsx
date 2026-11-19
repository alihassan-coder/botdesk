import { useEffect } from "react";
import Link from "next/link";
import { Monitor } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { budgetUse } from "@/lib/budget";
import { formatUsd } from "@/lib/format";
import { looserThan } from "@/lib/security-ceiling";
import { actions, useBotRoutines, useCurrentUser, useModel, useOrg } from "@/data/store";
import type { Bot, SecurityLevel } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { BotTools } from "@/features/bots/bot-tools";
import { EditBotDialog } from "@/features/bots/edit-bot-dialog";
import { BotMemories } from "@/features/memory/bot-memories";
import { RemoveBotButton } from "@/features/bots/remove-bot-button";
import { canChangeRoutine, toggle } from "@/features/routines/routine-card";
import { barColor } from "@/features/settings/budget-list";
import { securityLabel } from "@/features/bots/security-levels";

/** The details pane for a DM: who this bot is, its tools, routines, what it remembers, its computer. */
export function BotDetails({ bot }: { bot: Bot }) {
  return (
    <Tabs defaultValue="details" className="flex h-full flex-col gap-0">
      <TabsList className="mx-4 mt-3 grid grid-cols-5">
        <TabsTrigger value="details">Details</TabsTrigger>
        <TabsTrigger value="tools">Tools</TabsTrigger>
        <TabsTrigger value="routines">Routines</TabsTrigger>
        <TabsTrigger value="memory">Memory</TabsTrigger>
        <TabsTrigger value="computer">Computer</TabsTrigger>
      </TabsList>
      <div className="flex-1 overflow-y-auto p-4">
        <TabsContent value="details"><Profile bot={bot} /></TabsContent>
        <TabsContent value="tools"><BotTools bot={bot} /></TabsContent>
        <TabsContent value="routines"><Routines botId={bot.id} /></TabsContent>
        <TabsContent value="memory"><BotMemories bot={bot} compact /></TabsContent>
        <TabsContent value="computer"><Computer bot={bot} /></TabsContent>
      </div>
    </Tabs>
  );
}

function Profile({ bot }: { bot: Bot }) {
  const model = useModel(bot.modelId);
  // Any member can edit a bot; removing one takes an owner or admin.
  const canRemove = useCurrentUser().role !== "member";

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col items-start gap-3">
        <BotAvatar name={bot.name} color={bot.avatarColor} size="lg" />
        <div>
          <h2 className="text-lg font-semibold tracking-tight">{bot.name}</h2>
          <p className="text-sm text-muted-foreground">{bot.role} · @{bot.handle}</p>
        </div>
        {bot.description && <p className="text-sm leading-relaxed">{bot.description}</p>}
        <div className="flex gap-2">
          <EditBotDialog bot={bot} />
          {canRemove && <RemoveBotButton bot={bot} />}
        </div>
      </div>
      <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-2.5 text-sm">
        <dt className="text-muted-foreground">Model</dt>
        <dd>{model?.name ?? (bot.modelId || "Organization default")}</dd>
        <dt className="text-muted-foreground">Security level</dt>
        <dd><BotLevel level={bot.securityLevel} /></dd>
        <dt className="text-muted-foreground">Computer</dt>
        <dd><Badge variant="secondary">Coming soon</Badge></dd>
      </dl>
      <BudgetThisMonth bot={bot} />
    </div>
  );
}

/** Spend this month against the bot's budget (0 = no limit), fresh each time the pane opens. */
function BudgetThisMonth({ bot }: { bot: Bot }) {
  useEffect(() => {
    void actions.loadUsage();
  }, [bot.id]);
  const use = budgetUse(bot.spentThisMonthUsd, bot.monthlyBudgetUsd);

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex justify-between gap-2">
        <span className="text-muted-foreground">Budget this month</span>
        <span className="tabular-nums">
          {use.level === "none" ? `${formatUsd(bot.spentThisMonthUsd)} · no limit` : `${formatUsd(bot.spentThisMonthUsd)} of ${formatUsd(bot.monthlyBudgetUsd)}`}
        </span>
      </div>
      {use.level !== "none" && <Progress value={use.percent} className={barColor(use.level)} aria-label="Budget used" />}
      {use.level === "near" && <p className="text-xs text-muted-foreground">Close to its budget. Raise it with Edit if it needs more this month.</p>}
      {use.level === "reached" && (
        <p className="text-xs text-destructive">Reached its budget: it won&apos;t reply until you raise it with Edit or the month ends.</p>
      )}
    </div>
  );
}

function Routines({ botId }: { botId: string }) {
  const routines = useBotRoutines(botId);
  const me = useCurrentUser();
  if (routines.length === 0) {
    return <Empty text="No routines yet. Create one on the Routines page and this bot runs it on schedule, in your chat." />;
  }

  return (
    <ul className="flex flex-col gap-2">
      {routines.map((r) => (
        <li key={r.id} className="flex items-start gap-3 rounded-xl border p-3">
          <div className="min-w-0 flex-1">
            <Link href="/routines" className="text-sm font-medium hover:underline">{r.name}</Link>
            <p className="text-xs text-muted-foreground">{r.schedule}{r.timezone ? ` (${r.timezone})` : ""}</p>
          </div>
          <Switch checked={r.enabled} disabled={!canChangeRoutine(r, me)} onCheckedChange={() => void toggle(r)} aria-label={`Run ${r.name}`} />
        </li>
      ))}
    </ul>
  );
}

/** Bot computers aren't built yet (roadmap: "Bot computers"), so the tab says so plainly. */
function Computer({ bot }: { bot: Bot }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="grid aspect-[16/10] place-items-center rounded-xl border border-dashed bg-muted/50 text-muted-foreground">
        <Monitor className="size-8" aria-hidden />
      </div>
      <div className="flex items-center gap-2">
        <p className="text-sm font-medium">{bot.name}&apos;s computer</p>
        <Badge variant="secondary">Coming soon</Badge>
      </div>
      <p className="text-xs text-muted-foreground">
        Each bot will get its own computer with a browser, for websites and apps that have no integration. You&apos;ll watch it live and take over to sign in. Until then, bots work through connected apps.
      </p>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="py-6 text-center text-sm text-muted-foreground">{text}</p>;
}

/** The bot's own level, and the organization's ceiling when that's lower (it's what applies). */
function BotLevel({ level }: { level: SecurityLevel }) {
  const ceiling = useOrg().maxSecurityLevel;
  if (!looserThan(level, ceiling)) return securityLabel(level);
  return (
    <>
      {securityLabel(level)}
      <span className="block text-xs text-muted-foreground">Capped at {securityLabel(ceiling)} by the organization</span>
    </>
  );
}
