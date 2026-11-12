import type { Org } from "@/data/types";

/** An organization's plan as people read it, e.g. under its name in the sidebar. */
export const PLAN_LABEL: Record<Org["plan"], string> = {
  "self-hosted": "Self-hosted",
  free: "Free plan",
  pro: "Pro plan",
  team: "Team plan",
};
