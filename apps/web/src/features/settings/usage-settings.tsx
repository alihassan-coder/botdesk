"use client";

import { useEffect } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCount, formatUsd } from "@/lib/format";
import { actions, useBots, useUsage, useUsageLoading } from "@/data/store";
import { SettingsSection } from "./settings-shell";
import { SpendChart } from "./spend-chart";
import { BudgetList } from "./budget-list";
import { OrgBudget } from "./org-budget";

/** Settings → Usage & budgets: what the team spent, and how close each bot is to its limit. */
export function UsageSettings() {
  const usage = useUsage();
  const loading = useUsageLoading();
  const bots = useBots();

  // Spend moves with every reply: fetch the latest whenever this screen opens.
  useEffect(() => {
    void actions.loadUsage();
  }, []);

  const lastDays = usage.days.reduce((sum, d) => sum + d.tokensUsd + d.computerUsd, 0);

  return (
    <div className="flex flex-col gap-8">
      <SettingsSection title="Usage" description="Model tokens and computer time across all bots. Days and months are in UTC.">
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label={`Last ${usage.days.length || 14} days`} value={loading ? null : formatUsd(lastDays)} />
          <Stat label="Spent this month" value={loading ? null : formatUsd(usage.monthToDateUsd)} />
          <OrgBudget spentUsd={usage.monthToDateUsd} budgetUsd={usage.orgBudgetUsd} loading={loading} />
        </div>
        {usage.unpricedTokens > 0 && (
          <p className="text-sm text-muted-foreground">
            {formatCount(usage.unpricedTokens)} tokens this month came from models without a known price (like your own
            servers), so they aren&apos;t in these totals or counted against budgets.
          </p>
        )}
        {loading ? <Skeleton className="h-64 w-full rounded-2xl" /> : <SpendChart usage={usage.days} />}
      </SettingsSection>

      <SettingsSection
        title="Budgets"
        description="A bot stops before a reply that would take it past its budget, and says so in the chat. Change a bot's budget in its details pane."
      >
        <BudgetList bots={bots} />
      </SettingsSection>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-2xl border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      {value === null ? (
        <Skeleton className="mt-2 h-7 w-24" />
      ) : (
        <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
      )}
    </div>
  );
}
