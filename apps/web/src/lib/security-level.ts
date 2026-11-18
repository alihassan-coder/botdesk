import type { SecurityLevel } from "@/data/types";

/** Strictest first, as the API's `runtime/policy.py` orders them. */
const STRICTEST_FIRST: SecurityLevel[] = ["read-only", "ask-before-acting", "autonomous"];

/** The strictest of these levels (GLOSSARY: "the strictest of org, bot and routine wins"). */
export function strictestLevel(...levels: [SecurityLevel, ...SecurityLevel[]]): SecurityLevel {
  return levels.reduce((a, b) => (STRICTEST_FIRST.indexOf(b) < STRICTEST_FIRST.indexOf(a) ? b : a));
}
