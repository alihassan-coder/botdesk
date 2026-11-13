import type { PolicyDecision, RiskClass, SecurityLevel } from "@/data/types";

/**
 * What each security level means, in plain words (GLOSSARY.md → Security level).
 * Shared by the create-bot form, the details pane and Settings → Security.
 */
export const SECURITY_LEVELS: { value: SecurityLevel; label: string; description: string }[] = [
  {
    value: "read-only",
    label: "Read only",
    description: "Looks things up and keeps internal notes. Never drafts, changes or sends anything in your other apps.",
  },
  {
    value: "ask-before-acting",
    label: "Ask before acting",
    description: "Reads and keeps notes on its own. Asks you before drafting, sending, spending, deleting or using a login.",
  },
  {
    value: "autonomous",
    label: "Autonomous within limits",
    description: "Drafts and sends on its own, within its budget. Still asks before spending money, deleting or using a login.",
  },
];

export const securityLabel = (level: SecurityLevel) => SECURITY_LEVELS.find((l) => l.value === level)?.label ?? level;

/** Every risk class, safest first (the columns of the table in ADR 0004). */
export const RISK_CLASSES: RiskClass[] = ["read", "write-internal", "write-external", "external-send", "spend", "destructive", "credential"];

/**
 * What each level does with each kind of action: run it (auto), ask first (ask) or refuse (deny).
 * The table from ADR 0004, the same as apps/api/src/runtime/policy.py. On top of it, once a run
 * has read outside content (it's tainted), the rules only get stricter:
 * - an action above write-internal the table would run on its own asks instead; one the table
 *   refuses stays refused (Read only still denies), so taint never turns a "deny" into "ask";
 * - a tool that can reach any address (egress "open") counts as external-send, even a read,
 *   since it could leak data in the address it calls.
 */
export const POLICY: Record<SecurityLevel, Record<RiskClass, PolicyDecision>> = {
  "read-only": row("auto", "auto", "deny", "deny", "deny", "deny", "deny"),
  "ask-before-acting": row("auto", "auto", "ask", "ask", "ask", "ask", "ask"),
  autonomous: row("auto", "auto", "auto", "auto", "ask", "ask", "ask"),
};

function row(...decisions: PolicyDecision[]): Record<RiskClass, PolicyDecision> {
  return Object.fromEntries(RISK_CLASSES.map((risk, i) => [risk, decisions[i]])) as Record<RiskClass, PolicyDecision>;
}
