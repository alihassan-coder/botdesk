import type { SecurityLevel } from "@/data/types";

/** Strictest first, as in ADR 0004 and apps/api/src/runtime/policy.py. */
const ORDER: SecurityLevel[] = ["read-only", "ask-before-acting", "autonomous"];

/** The level that applies: the strictest of those given, e.g. the organization's ceiling and a bot's level. */
export const strictestLevel = (...levels: SecurityLevel[]): SecurityLevel => ORDER.find((l) => levels.includes(l)) ?? "read-only";

/** Whether `level` lets a bot do more on its own than `ceiling` allows (the API's rule too). */
export const looserThan = (level: SecurityLevel, ceiling: SecurityLevel) => ORDER.indexOf(level) > ORDER.indexOf(ceiling);
