import { describe, expect, it } from "vitest";
import type { PolicyDecision, RiskClass, SecurityLevel } from "@/data/types";
import { POLICY, RISK_CLASSES, SECURITY_LEVELS } from "./security-levels";

/* Every cell of ADR 0004's table, written out once more so a typo in either copy shows up.
 * Must match apps/api/src/runtime/policy.py. */
const EXPECTED: [SecurityLevel, RiskClass, PolicyDecision][] = [
  ["read-only", "read", "auto"],
  ["read-only", "write-internal", "auto"],
  ["read-only", "write-external", "deny"],
  ["read-only", "external-send", "deny"],
  ["read-only", "spend", "deny"],
  ["read-only", "destructive", "deny"],
  ["read-only", "credential", "deny"],
  ["ask-before-acting", "read", "auto"],
  ["ask-before-acting", "write-internal", "auto"],
  ["ask-before-acting", "write-external", "ask"],
  ["ask-before-acting", "external-send", "ask"],
  ["ask-before-acting", "spend", "ask"],
  ["ask-before-acting", "destructive", "ask"],
  ["ask-before-acting", "credential", "ask"],
  ["autonomous", "read", "auto"],
  ["autonomous", "write-internal", "auto"],
  ["autonomous", "write-external", "auto"],
  ["autonomous", "external-send", "auto"],
  ["autonomous", "spend", "ask"],
  ["autonomous", "destructive", "ask"],
  ["autonomous", "credential", "ask"],
];

describe("POLICY", () => {
  it.each(EXPECTED)("%s + %s → %s", (level, risk, decision) => {
    expect(POLICY[level][risk]).toBe(decision);
  });

  it("covers 3 levels × 7 risk classes and nothing else", () => {
    expect(RISK_CLASSES).toHaveLength(7);
    expect(SECURITY_LEVELS.map((l) => l.value)).toEqual(["read-only", "ask-before-acting", "autonomous"]);
    for (const level of SECURITY_LEVELS) expect(Object.keys(POLICY[level.value]).sort()).toEqual([...RISK_CLASSES].sort());
  });

  it("Read only is never described as drafting outside", () => {
    const readOnly = SECURITY_LEVELS.find((l) => l.value === "read-only")!.description;
    expect(readOnly).toMatch(/Never drafts/);
  });
});
