import { useEffect } from "react";
import { Monitor } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { budgetUse } from "@/lib/budget";
import { formatUsd } from "@/lib/format";
import { actions, useBotRoutines, useCurrentUser, useModel } from "@/data/store";
import type { Bot } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { EditBotDialog } from "@/features/bots/edit-bot-dialog";
import { BotMemories } from "@/features/memory/bot-memories";
import { RemoveBotButton } from "@/features/bots/remove-bot-button";
import { barColor } from "@/features/settings/budget-list";
import { securityLabel } from "@/features/bots/security-levels";

/** The details pane for a DM: who this bot is, its routines, what it remembers, its computer. */
export function BotDetails({ bot }: { bot: Bot }) {
  return (
    <Tabs defaultValue="details" className="flex h-full flex-col gap-0">
      <TabsList className="mx-4 mt-3 grid grid-cols-4">
        <TabsTrigger value="details">Details</TabsTrigger>
        <TabsTrigger value="routines">Routines</TabsTrigger>
        <TabsTrigger value="memory">Memory</TabsTrigger>
        <TabsTrigger value="computer">Computer</TabsTrigger>
      </TabsList>
      <div className="flex-1 overflow-y-auto p-4">
        <TabsContent value="details"><Profile bot={bot} /></TabsContent>
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
        <dd>{securityLabel(bot.securityLevel)}</dd>
        <dt className="text-muted-foreground">Computer</dt>
        <dd>{bot.computerMode === "own" ? "Its own" : bot.computerMode === "shared" ? "Shared" : "None"}</dd>
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
  if (routines.length === 0) return <Empty text="No routines yet. Ask the bot to do something every week and it can save it as one." />;

  return (
    <ul className="flex flex-col gap-2">
      {routines.map((r) => (
        <li key={r.id} className="flex items-start gap-3 rounded-xl border p-3">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">{r.name}</p>
            <p className="text-xs text-muted-foreground">{r.schedule}</p>
          </div>
          <Switch checked={r.enabled} onCheckedChange={() => actions.toggleRoutine(r.id)} aria-label={`Run ${r.name}`} />
        </li>
      ))}
    </ul>
  );
}

function Computer({ bot }: { bot: Bot }) {
  if (bot.computerMode === "none") return <Empty text={`${bot.name} works through apps only, without a computer of its own.`} />;
  return (
    <div className="flex flex-col gap-2">
      <div className="grid aspect-[16/10] place-items-center rounded-xl border bg-muted text-muted-foreground">
        <Monitor className="size-8" />
      </div>
      <p className="text-sm font-medium">{bot.name}&apos;s screen</p>
      <p className="text-xs text-muted-foreground">Live view and take over arrive with the Computer view.</p>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="py-6 text-center text-sm text-muted-foreground">{text}</p>;
}
