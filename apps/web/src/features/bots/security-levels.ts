import type { PolicyDecision, RiskClass, SecurityLevel } from "@/data/types";

/**
 * What each security level means, in plain words (GLOSSARY.md → Security level).
 * Shared by the create-bot form, the details pane and Settings → Security.
 */
export const SECURITY_LEVELS: { value: SecurityLevel; label: string; description: string }[] = [
  { value: "read-only", label: "Read only", description: "Can look things up and draft, but never changes or sends anything." },
  { value: "ask-before-acting", label: "Ask before acting", description: "Does the safe work itself and asks you before sending, spending or deleting." },
  { value: "autonomous", label: "Autonomous within limits", description: "Acts on its own within its budget. Still asks before anything that can't be undone." },
];

export const securityLabel = (level: SecurityLevel) => SECURITY_LEVELS.find((l) => l.value === level)?.label ?? level;

/**
 * What each level does with each kind of action: run it (auto), ask first (ask) or refuse (deny).
 * From docs/architecture/high-level.md §9.2. Logins are never automatic; nor are deletes in v1.
 */
export const POLICY: Record<SecurityLevel, Record<RiskClass, PolicyDecision>> = {
  "read-only": { read: "auto", "write-internal": "auto", "external-send": "deny", spend: "deny", destructive: "deny", credential: "deny" },
  "ask-before-acting": { read: "auto", "write-internal": "auto", "external-send": "ask", spend: "ask", destructive: "ask", credential: "ask" },
  autonomous: { read: "auto", "write-internal": "auto", "external-send": "auto", spend: "ask", destructive: "ask", credential: "ask" },
};
