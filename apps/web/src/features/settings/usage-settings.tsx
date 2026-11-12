"use client";

import Link from "next/link";
import { TriangleAlert } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { formatUsd } from "@/lib/format";
import { useBots, useThreads, useUsage } from "@/data/store";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { SettingsSection } from "./settings-shell";
import { SpendChart } from "./spend-chart";

/** Settings → Usage & budgets: what the team spent, and how close each bot is to its limit. */
export function UsageSettings() {
  const usage = useUsage();
  const bots = useBots();
  const threads = useThreads();

  const total = usage.reduce((sum, d) => sum + d.tokensUsd + d.computerUsd, 0);
  const budget = bots.reduce((sum, b) => sum + b.monthlyBudgetUsd, 0);
  const spent = bots.reduce((sum, b) => sum + b.spentThisMonthUsd, 0);

  return (
    <div className="flex flex-col gap-8">
      <SettingsSection title="Usage" description="Model tokens and computer time across all bots.">
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label="Last 14 days" value={formatUsd(total)} />
          <Stat label="Spent this month" value={formatUsd(spent)} />
          <Stat label="Monthly budgets" value={formatUsd(budget)} />
        </div>
        <SpendChart usage={usage} />
      </SettingsSection>

      <SettingsSection title="Budgets" description="A bot pauses when it reaches its budget and tells you. Change a budget in its details pane.">
        <ul className="flex flex-col divide-y rounded-2xl border">
          {[...bots].sort((a, b) => b.spentThisMonthUsd / b.monthlyBudgetUsd - a.spentThisMonthUsd / a.monthlyBudgetUsd).map((bot) => {
            const share = Math.min(100, (bot.spentThisMonthUsd / bot.monthlyBudgetUsd) * 100);
            const thread = threads.find((t) => t.botId === bot.id);
            return (
              <li key={bot.id} className="flex items-center gap-3 p-3">
                <BotAvatar name={bot.name} color={bot.avatarColor} size="sm" />
                <Link href={thread ? `/chat/${thread.id}` : "#"} className="w-36 truncate text-sm font-medium hover:underline">{bot.name}</Link>
                <Progress value={share} className="flex-1" aria-label={`${bot.name} budget used`} />
                <span className="w-32 text-right text-sm tabular-nums text-muted-foreground">
                  {formatUsd(bot.spentThisMonthUsd)} / {formatUsd(bot.monthlyBudgetUsd)}
                </span>
                {share >= 70 ? (
                  <TriangleAlert className="size-4 text-working" aria-label="Close to its budget" />
                ) : (
                  <span className="size-4" aria-hidden />
                )}
              </li>
            );
          })}
        </ul>
      </SettingsSection>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
    </div>
  );
}
