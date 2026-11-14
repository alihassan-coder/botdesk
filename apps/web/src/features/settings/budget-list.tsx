import Link from "next/link";
import { CircleAlert, TriangleAlert } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { budgetOrder, budgetUse, type BudgetLevel } from "@/lib/budget";
import { formatUsd } from "@/lib/format";
import { useThreads } from "@/data/store";
import type { Bot } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";

/** Every bot's spend this month against its budget, the closest to its limit first. */
export function BudgetList({ bots }: { bots: Bot[] }) {
  const threads = useThreads();
  if (bots.length === 0) {
    return <p className="rounded-2xl border p-4 text-sm text-muted-foreground">No bots yet. Hire one and its budget shows here.</p>;
  }
  const sorted = [...bots].sort(
    (a, b) => budgetOrder(b.spentThisMonthUsd, b.monthlyBudgetUsd) - budgetOrder(a.spentThisMonthUsd, a.monthlyBudgetUsd),
  );

  return (
    <ul className="flex flex-col divide-y rounded-2xl border">
      {sorted.map((bot) => {
        const use = budgetUse(bot.spentThisMonthUsd, bot.monthlyBudgetUsd);
        const thread = threads.find((t) => t.kind === "dm" && t.botId === bot.id);
        return (
          <li key={bot.id} className="flex items-center gap-3 p-3">
            <BotAvatar name={bot.name} color={bot.avatarColor} size="sm" />
            {/* Narrow: name and amount on one line, the bar under them. Wide: name, bar, amount in a row. */}
            <div className="grid min-w-0 flex-1 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 @lg:grid-cols-[9rem_minmax(0,1fr)_auto]">
              <Link href={thread ? `/chat/${thread.id}` : "#"} className="-my-1 truncate py-1 text-sm font-medium hover:underline">
                {bot.name}
              </Link>
              <span className="text-right text-sm whitespace-nowrap tabular-nums text-muted-foreground @lg:order-last @lg:min-w-36">
                {formatUsd(bot.spentThisMonthUsd)}
                {use.level !== "none" && <> / {formatUsd(bot.monthlyBudgetUsd)}</>}
              </span>
              {use.level === "none" ? (
                <span className="col-span-2 text-xs text-muted-foreground @lg:col-span-1">No limit</span>
              ) : (
                <Progress value={use.percent} className={cn("col-span-2 @lg:col-span-1", barColor(use.level))} aria-label={`${bot.name} budget used`} />
              )}
            </div>
            <LevelIcon level={use.level} />
          </li>
        );
      })}
    </ul>
  );
}

/** The bar turns amber near the limit and red once it's reached. */
export function barColor(level: BudgetLevel) {
  if (level === "reached") return "[&>[data-slot=progress-indicator]]:bg-destructive";
  if (level === "near") return "[&>[data-slot=progress-indicator]]:bg-working";
  return undefined;
}

function LevelIcon({ level }: { level: BudgetLevel }) {
  if (level === "reached") return <CircleAlert className="size-4 shrink-0 text-destructive" role="img" aria-label="Reached its budget" />;
  if (level === "near") return <TriangleAlert className="size-4 shrink-0 text-working" role="img" aria-label="Close to its budget" />;
  return <span className="size-4 shrink-0" aria-hidden />;
}
