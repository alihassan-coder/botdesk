import type { User } from "@/data/types";

/**
 * First-time setup (/welcome) is for the owner of a brand-new organization: one with no bots
 * yet. Members joining by invite land in a team that's already set up, and the demo has bots.
 * Finishing or skipping setup is remembered per organization in this browser, so it never nags.
 */
export function needsOnboarding(s: { demo: boolean; botsLoading: boolean; botCount: number; role: User["role"]; done: boolean }) {
  return !s.demo && !s.botsLoading && s.botCount === 0 && s.role === "owner" && !s.done;
}
