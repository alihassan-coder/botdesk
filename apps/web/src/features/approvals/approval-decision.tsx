import { Check, Clock, PencilLine, X } from "lucide-react";
import { TimeAgo } from "@/components/time-ago";
import { useCurrentUser, useUser } from "@/data/store";
import type { Approval, ApprovalStatus } from "@/data/types";

type Decided = Exclude<ApprovalStatus, "pending">;

const LINE: Record<Decided, { icon: React.ReactNode; text: (who: string) => string; already: (who: string) => string }> = {
  approved: {
    icon: <Check className="size-3.5 text-success" />,
    text: (who) => `Approved by ${who}`,
    already: (who) => `${who} already approved this, so your changes weren't used.`,
  },
  edited: {
    icon: <PencilLine className="size-3.5 text-success" />,
    text: (who) => `Edited and approved by ${who}`,
    already: (who) => `${who} already edited and approved this, so your changes weren't used.`,
  },
  denied: {
    icon: <X className="size-3.5 text-destructive" />,
    text: (who) => `Denied by ${who}`,
    already: (who) => `${who} already denied this, so your changes weren't used.`,
  },
  expired: {
    icon: <Clock className="size-3.5 text-muted-foreground" />,
    text: () => "Expired, so the bot didn't do it",
    already: () => "This expired before your changes were sent.",
  },
};

/** Who decided, as the card says it: "you", a teammate's name, or "a teammate". */
function useDecider(approval: Approval): { who: string; isMe: boolean } {
  const me = useCurrentUser();
  const decider = useUser(approval.decidedBy);
  const isMe = approval.decidedBy !== undefined && approval.decidedBy === me.id;
  return { who: isMe ? "you" : (decider?.name ?? approval.decidedByName ?? "a teammate"), isMe };
}

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/**
 * Someone else decided while you were editing: "Omar already approved this, so your changes
 * weren't used." Empty when it was you, or while it still waits.
 */
export function useAlreadyDecidedText(approval: Approval): string {
  const { who, isMe } = useDecider(approval);
  if (approval.status === "pending" || isMe) return "";
  return capitalize(LINE[approval.status].already(who));
}

/**
 * After a decision: "Approved by you · 5m", "Edited and approved by Sara · 1h", "Denied by Ali"…
 * It takes focus (tabIndex -1) once you've decided, so keyboard users aren't left on a button
 * that's gone. It renders inside the card's live region, which announces it.
 */
export function ApprovalDecision({ approval, ref }: { approval: Approval; ref?: React.Ref<HTMLParagraphElement> }) {
  const { who } = useDecider(approval);
  if (approval.status === "pending") return null;
  const line = LINE[approval.status];

  return (
    <p
      ref={ref}
      tabIndex={-1}
      className="mt-2 flex items-center gap-1.5 rounded-sm text-xs text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
    >
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
