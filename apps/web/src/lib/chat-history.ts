import type { HistoryRetentionDays } from "@/data/types";

/** How long messages are kept (ADR 0019); null keeps them forever. */
export type Retention = HistoryRetentionDays | null;

/** The choices for "Delete messages older than". */
export const RETENTION_CHOICES: { days: Retention; label: string }[] = [
  { days: null, label: "Never" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 180, label: "180 days" },
  { days: 365, label: "1 year" },
];

/** "Never", "30 days", "1 year". */
export function retentionLabel(days: Retention): string {
  return RETENTION_CHOICES.find((c) => c.days === days)?.label ?? `${days} days`;
}

/**
 * Whether going from one limit to another deletes messages the old one kept: any limit after
 * Never, or a shorter one. Those can't be undone, so they ask first; a longer limit or Never doesn't.
 */
export function deletesMore(from: Retention, to: Retention): to is HistoryRetentionDays {
  return to !== null && (from === null || to < from);
}

/** A Select's value for a retention ("never", "90"), and back. */
export const retentionValue = (days: Retention) => (days === null ? "never" : String(days));
export function retentionFromValue(value: string): Retention {
  return RETENTION_CHOICES.find((c) => retentionValue(c.days) === value)?.days ?? null;
}
