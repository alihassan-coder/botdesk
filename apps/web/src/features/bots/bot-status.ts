import type { BotStatus } from "@/data/types";

/**
 * How each bot status looks and reads, in one place.
 * amber = working, brand (ultramarine) = needs your approval, red = error, grey = sleeping.
 */
export const BOT_STATUS: Record<BotStatus, { label: string; dotClass: string }> = {
  idle: { label: "Ready", dotClass: "bg-success" },
  working: { label: "Working", dotClass: "bg-working" },
  "waiting-approval": { label: "Needs your approval", dotClass: "bg-brand" },
  sleeping: { label: "Sleeping", dotClass: "bg-sleeping" },
  error: { label: "Needs attention", dotClass: "bg-destructive" },
};
