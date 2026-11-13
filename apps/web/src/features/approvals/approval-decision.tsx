import { Check, Clock, PencilLine, X } from "lucide-react";
import { TimeAgo } from "@/components/time-ago";
import { useCurrentUser, useUser } from "@/data/store";
import type { Approval, ApprovalStatus } from "@/data/types";

const LINE: Record<Exclude<ApprovalStatus, "pending">, { icon: React.ReactNode; text: (who: string) => string }> = {
  approved: { icon: <Check className="size-3.5 text-success" />, text: (who) => `Approved by ${who}` },
  edited: { icon: <PencilLine className="size-3.5 text-success" />, text: (who) => `Edited and approved by ${who}` },
  denied: { icon: <X className="size-3.5 text-destructive" />, text: (who) => `Denied by ${who}` },
  expired: { icon: <Clock className="size-3.5 text-muted-foreground" />, text: () => "Expired, so the bot didn't do it" },
};

/** After a decision: "Approved by you · 5m", "Edited and approved by Sara · 1h", "Denied by Ali"… */
export function ApprovalDecision({ approval }: { approval: Approval }) {
  const me = useCurrentUser();
  const decider = useUser(approval.decidedBy);
  if (approval.status === "pending") return null;

  const who = approval.decidedBy === me.id ? "you" : (decider?.name ?? approval.decidedByName ?? "a teammate");
  const line = LINE[approval.status];

  return (
    <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground" role="status">
      {line.icon} {line.text(who)}
      {approval.decidedAt && (
        <>
          {" · "}
          <TimeAgo iso={approval.decidedAt} />
        </>
      )}
    </p>
  );
}
