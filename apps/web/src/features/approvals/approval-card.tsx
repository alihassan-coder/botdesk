import { useState } from "react";
import { Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TimeAgo } from "@/components/time-ago";
import { actions, useApproval, useCurrentUser, useUser } from "@/data/store";
import type { Approval } from "@/data/types";
import { PartCard } from "@/features/messages/part-card";
import { ApprovalEditor } from "./approval-editor";
import { RISK } from "./risk";

/**
 * A bot paused on a risky action. You see exactly what it wants to do and choose:
 * Approve, Deny, or Edit (change the details, then approve). Nothing happens until you decide.
 */
export function ApprovalCard({ approvalId }: { approvalId: string }) {
  const approval = useApproval(approvalId);
  const [isEditing, setIsEditing] = useState(false);

  if (!approval) return null;
  const risk = RISK[approval.riskClass];
  const isPending = approval.status === "pending";

  return (
    <PartCard className={isPending ? "border-brand/40 ring-4 ring-brand/5" : undefined}>
      <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-brand">
        <risk.icon className="size-3.5" /> {risk.label}
      </div>
      <h3 className="font-medium">{approval.title}</h3>
      <p className="mt-0.5 text-muted-foreground">{approval.summary}</p>

      {isEditing ? (
        <ApprovalEditor
          preview={approval.preview}
          onCancel={() => setIsEditing(false)}
          onApprove={(preview) => {
            actions.editAndApprove(approval.id, preview);
            setIsEditing(false);
          }}
        />
      ) : (
        <>
          {isPending && <PreviewFields preview={approval.preview} />}
          {isPending ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" onClick={() => actions.decideApproval(approval.id, "approved")}>
                <Check /> Approve
              </Button>
              <Button size="sm" variant="outline" onClick={() => setIsEditing(true)}>
                Edit
              </Button>
              <Button size="sm" variant="ghost" onClick={() => actions.decideApproval(approval.id, "denied")}>
                Deny
              </Button>
            </div>
          ) : (
            <Decision approval={approval} />
          )}
        </>
      )}
    </PartCard>
  );
}

/** The exact action: To, Subject, Body… Long values keep their line breaks. */
function PreviewFields({ preview }: { preview: Approval["preview"] }) {
  return (
    <dl className="mt-3 flex flex-col gap-2 rounded-xl bg-muted/60 p-3 text-[13px]">
      {preview.map((field) => (
        <div key={field.label} className="grid gap-0.5 sm:grid-cols-[72px_1fr] sm:gap-3">
          <dt className="text-muted-foreground">{field.label}</dt>
          <dd className="break-words whitespace-pre-wrap">{field.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** After a decision: "✓ Approved by you · 5m" or "Denied by Sara · 1h". */
function Decision({ approval }: { approval: Approval }) {
  const me = useCurrentUser();
  const decider = useUser(approval.decidedBy);
  const who = approval.decidedBy === me.id ? "you" : (decider?.name ?? "a teammate");

  const line = {
    approved: { icon: <Check className="size-3.5 text-success" />, text: `Approved by ${who}` },
    denied: { icon: <X className="size-3.5 text-destructive" />, text: `Denied by ${who}` },
    expired: { icon: <X className="size-3.5 text-muted-foreground" />, text: "Expired before anyone decided" },
    pending: { icon: null, text: "" },
  }[approval.status];

  return (
    <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
      {line.icon} {line.text}
      {approval.decidedAt && (
        <>
          {" · "}
          <TimeAgo iso={approval.decidedAt} />
        </>
      )}
    </p>
  );
}
