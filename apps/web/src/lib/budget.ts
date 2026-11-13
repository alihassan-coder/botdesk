/**
 * How close something is to its monthly budget. A budget of 0 (or none) is no limit.
 * "near" from 80% used, so there's time to raise it before replies stop.
 */
export type BudgetLevel = "none" | "ok" | "near" | "reached";

export const NEAR_BUDGET = 0.8;

export interface BudgetUse {
  level: BudgetLevel;
  /** 0–100 for a progress bar; 0 when there's no limit. */
  percent: number;
}

export function budgetUse(spentUsd: number, budgetUsd: number | undefined): BudgetUse {
  if (!budgetUsd || budgetUsd <= 0) return { level: "none", percent: 0 };
  const share = spentUsd / budgetUsd;
  const percent = Math.min(100, Math.max(0, share * 100));
  return { level: share >= 1 ? "reached" : share >= NEAR_BUDGET ? "near" : "ok", percent };
}

/** For sorting: the closest to its limit first, bots without a limit last. */
export function budgetOrder(spentUsd: number, budgetUsd: number | undefined): number {
  return budgetUsd && budgetUsd > 0 ? spentUsd / budgetUsd : -1;
}
