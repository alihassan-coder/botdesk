import { useState } from "react";
import { toast } from "sonner";
import { actions, useCurrentUser, useOrg } from "@/data/store";
import type { SecurityLevel } from "@/data/types";
import { SecurityLevelPicker } from "@/features/bots/security-level-picker";

/**
 * The organization's ceiling (ADR 0004): no bot acts above it, whatever its own level, and
 * lowering it applies from every bot's next action. Lowering it below the default for new bots
 * lowers the default too. Owners and admins change it.
 */
export function SecurityCeiling() {
  const saved = useOrg().maxSecurityLevel;
  const canEdit = useCurrentUser().role !== "member";
  // The level being saved shows at once; a refusal puts the saved one back.
  const [saving, setSaving] = useState<SecurityLevel | null>(null);

  async function change(level: SecurityLevel) {
    setSaving(level);
    const result = await actions.setMaxSecurityLevel(level);
    setSaving(null);
    if (!result.ok) return void toast.error(result.error);
    toast.success("Highest security level saved");
  }

  return (
    <>
      <SecurityLevelPicker label="Highest security level" value={saving ?? saved} onChange={(level) => void change(level)} disabled={!canEdit} />
      {!canEdit && <p className="mt-3 text-sm text-muted-foreground">Only owners and admins can change the highest level.</p>}
    </>
  );
}
