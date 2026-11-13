import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { budgetUse } from "@/lib/budget";
import { formatUsd } from "@/lib/format";
import { actions, useCurrentUser } from "@/data/store";
import { barColor } from "./budget-list";

/**
 * What all the org's bots together may spend a month. Owners and admins can change it;
 * an empty or 0 budget means no limit.
 */
export function OrgBudget({ spentUsd, budgetUsd, loading }: { spentUsd: number; budgetUsd?: number; loading: boolean }) {
  const canEdit = useCurrentUser().role !== "member";
  const [editing, setEditing] = useState(false);
  const use = budgetUse(spentUsd, budgetUsd);

  return (
    <div className="flex flex-col gap-2 rounded-2xl border p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm text-muted-foreground">Organization budget</p>
        {canEdit && !editing && !loading && (
          <Button variant="ghost" size="sm" className="-mt-1.5 -mr-2 h-7" onClick={() => setEditing(true)}>
            {budgetUsd ? "Change" : "Set"}
          </Button>
        )}
      </div>
      {loading ? (
        <Skeleton className="h-7 w-24" />
      ) : editing ? (
        <BudgetForm budgetUsd={budgetUsd} onDone={() => setEditing(false)} />
      ) : (
        <>
          <p className="text-2xl font-semibold tracking-tight tabular-nums">{budgetUsd ? formatUsd(budgetUsd) : "No limit"}</p>
          {use.level !== "none" && (
            <Progress value={use.percent} className={barColor(use.level)} aria-label="Organization budget used" />
          )}
        </>
      )}
    </div>
  );
}

function BudgetForm({ budgetUsd, onDone }: { budgetUsd?: number; onDone: () => void }) {
  const [value, setValue] = useState(budgetUsd ? String(budgetUsd) : "");
  const [saving, startSaving] = useTransition();

  const save = () =>
    startSaving(async () => {
      const usd = Math.max(0, Math.round(Number(value) || 0));
      const result = await actions.setOrgBudget(usd || null);
      if (!result.ok) return void toast.error(result.error);
      toast.success(usd ? `Budget set to ${formatUsd(usd)} a month` : "Budget removed");
      onDone();
    });

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <Input
        type="number"
        min={0}
        step={10}
        inputMode="numeric"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="No limit"
        aria-label="Organization budget per month, in US dollars"
        autoFocus
      />
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={saving}>Save</Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}
