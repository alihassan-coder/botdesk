import { useEffect, useRef, useState } from "react";
import { Check, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { actions, useApproval } from "@/data/store";
import type { Approval } from "@/data/types";
import { useNow } from "@/hooks/use-now";
import { explainReason, expiryLabel } from "@/lib/approval-text";
import { PartCard } from "@/features/messages/part-card";
import { ApprovalDecision, useAlreadyDecidedText } from "./approval-decision";
import { ApprovalEditor } from "./approval-editor";
import { RISK } from "./risk";

/**
 * A bot paused on a risky action. You see exactly what it wants to do and why it asked, then
 * choose: Approve, Deny, or Edit (change the details, then approve). Nothing happens until you decide.
 *
 * Focus follows the flow: Edit focuses the form's first field, Cancel returns to Edit, and your
 * decision moves focus to the decision line, which sits in a live region that stays mounted,
 * so the decision is announced whoever made it. If someone else decides while your edit is
 * open, the form closes, the card says your changes weren't used, and focus (if it was in the
 * form) moves to the decision line once.
 */
export function ApprovalCard({ approvalId }: { approvalId: string }) {
  const approval = useApproval(approvalId);
  const [isEditing, setIsEditing] = useState(false);
  /** Someone else decided while your edit was open: the form is gone, and the card says so. */
  const [editOverruled, setEditOverruled] = useState(false);
  const [deciding, setDeciding] = useState<"approve" | "deny" | null>(null);
  const editButton = useRef<HTMLButtonElement>(null);
  const decisionLine = useRef<HTMLParagraphElement>(null);
  /** Where focus goes after the next render: back to Edit, or to the decision line. */
  const focusNext = useRef<"edit" | "decision" | null>(null);
  const isPending = approval?.status === "pending";

  // Decided elsewhere while you were editing: close the edit (adjusting state while rendering,
  // so it happens once, on the render that sees the decision).
  if (isEditing && approval && !isPending) {
    setIsEditing(false);
    setEditOverruled(true);
  }

  useEffect(() => {
    // The form had focus and is gone: move it to the decision line, once. If you were somewhere
    // else, focus stays there.
    if (editOverruled && document.activeElement === document.body) decisionLine.current?.focus();
  }, [editOverruled]);

  useEffect(() => {
    const target = focusNext.current === "edit" ? editButton.current : focusNext.current === "decision" ? decisionLine.current : null;
    if (!target) return;
    focusNext.current = null;
    target.focus();
  });

  if (!approval) return null;
  const risk = RISK[approval.riskClass];

  async function decide(decision: "approve" | "deny") {
    setDeciding(decision);
    const result = await actions.decideApproval(approvalId, decision);
    setDeciding(null);
    if (result.ok) focusNext.current = "decision";
    else toast.error(result.error);
  }

  function closeEditor(decided: boolean) {
    focusNext.current = decided ? "decision" : "edit";
    setIsEditing(false);
  }

  return (
    <PartCard className={isPending ? "border-brand/40 ring-4 ring-brand/5" : undefined} aria-label={`Approval: ${approval.title}`} role="group">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-brand">
        <risk.icon className="size-3.5" /> {risk.label}
        {isPending && approval.expiresAt && <Expiry iso={approval.expiresAt} />}
      </div>
      <h3 className="font-medium">{approval.title}</h3>
      <p className="mt-0.5 text-muted-foreground">{approval.summary}</p>
      {approval.reason && <p className="mt-1 text-xs text-muted-foreground">{explainReason(approval.reason)}</p>}
      {isPending && approval.tainted && <TaintWarning />}

      {/* Always mounted, so screen readers announce the decision when it arrives, yours or a teammate's. */}
      <div aria-live="polite" aria-atomic="true">
        {!isPending && (
          <>
            {editOverruled && <AlreadyDecided approval={approval} />}
            <ApprovalDecision approval={approval} ref={decisionLine} />
          </>
        )}
      </div>
      {isEditing && isPending ? (
        <ApprovalEditor approval={approval} onClose={closeEditor} />
      ) : isPending ? (
        <>
          <PreviewFields preview={approval.preview} />
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => decide("approve")} disabled={deciding !== null}>
              {deciding === "approve" ? <Spinner /> : <Check />} Approve
            </Button>
            <Button ref={editButton} size="sm" variant="outline" onClick={() => setIsEditing(true)} disabled={deciding !== null}>
              Edit
            </Button>
            <Button size="sm" variant="ghost" onClick={() => decide("deny")} disabled={deciding !== null}>
              {deciding === "deny" && <Spinner />} Deny
            </Button>
          </div>
        </>
      ) : null}
    </PartCard>
  );
}

/** Someone else decided while your edit was open: say who, rather than just dropping the form. */
function AlreadyDecided({ approval }: { approval: Approval }) {
  const text = useAlreadyDecidedText(approval);
  if (!text) return null;
  return <p className="mt-3 rounded-xl bg-muted/60 p-3 text-[13px]">{text}</p>;
}

/** The exact action: To, Subject, Body… Long values keep their line breaks. */
function PreviewFields({ preview }: { preview: Approval["preview"] }) {
  if (preview.length === 0) return null;
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

/** The run read text from outside (an email, a web page), which can try to steer a bot. */
function TaintWarning() {
  return (
    <Alert className="mt-3 border-working/40 bg-working/5">
      <ShieldAlert />
      <AlertTitle>This bot read outside content first</AlertTitle>
      <AlertDescription>Text from an email or web page can try to trick a bot. Check the details before you approve.</AlertDescription>
    </Alert>
  );
}

/** "Expires in 3 days", worked out in the browser only. */
function Expiry({ iso }: { iso: string }) {
  const now = useNow();
  if (now === null) return null;
  return <span className="ml-auto font-normal text-muted-foreground">{expiryLabel(iso, now)}</span>;
}
