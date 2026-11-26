import { useState } from "react";
import { toast } from "sonner";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Field, FieldContent, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { actions, useCurrentUser, useOrg } from "@/data/store";
import type { HistoryRetentionDays } from "@/data/types";
import { RETENTION_CHOICES, deletesMore, retentionFromValue, retentionLabel, retentionValue, type Retention } from "@/lib/chat-history";

/**
 * Settings → Organization's Chat history (ADR 0019): whether bots read a summary of older messages,
 * and after how long messages are deleted. A limit that deletes more than before asks first, since
 * it can't be undone. Owners and admins change them; members see them read-only.
 */
export function ChatHistory() {
  const org = useOrg();
  const canEdit = useCurrentUser().role !== "member";
  // What's being saved shows at once; a refusal puts the saved value back.
  const [summaries, setSummaries] = useState<boolean | null>(null);
  const [retention, setRetention] = useState<{ days: Retention } | null>(null);
  // A limit waiting for a yes. It stays set while the dialog closes, so its words don't change on the way out.
  const [asking, setAsking] = useState<HistoryRetentionDays>(30);
  const [confirming, setConfirming] = useState(false);

  async function saveSummaries(on: boolean) {
    setSummaries(on);
    const result = await actions.setChatHistory({ historySummaries: on });
    setSummaries(null);
    if (!result.ok) return void toast.error(result.error);
    toast.success(on ? "Bots now read a summary of older messages" : "Bots now read only the last 30 messages");
  }

  async function saveRetention(days: Retention) {
    setRetention({ days });
    const result = await actions.setChatHistory({ historyRetentionDays: days });
    setRetention(null);
    if (!result.ok) return void toast.error(result.error);
    toast.success(days === null ? "Messages are kept forever" : `Messages older than ${retentionLabel(days)} will be deleted every night`);
  }

  function pick(value: string) {
    const days = retentionFromValue(value);
    if (days === org.historyRetentionDays) return;
    if (!deletesMore(org.historyRetentionDays, days)) return void saveRetention(days);
    setAsking(days);
    setConfirming(true);
  }

  return (
    <>
      <FieldGroup>
        <Field orientation="horizontal">
          <FieldContent>
            <FieldLabel htmlFor="history-summaries">Bots read a summary of older messages</FieldLabel>
            <FieldDescription>
              A bot reads a chat&apos;s last 30 messages word for word. With this on, it also reads a short summary of the
              older ones, written by the bot&apos;s model with the organization&apos;s key: about one model call per 20 messages.
            </FieldDescription>
          </FieldContent>
          <Switch id="history-summaries" checked={summaries ?? org.historySummaries} disabled={!canEdit} onCheckedChange={(on) => void saveSummaries(on)} />
        </Field>
        <Field orientation="responsive">
          <FieldContent>
            <FieldLabel htmlFor="history-retention">Delete messages older than</FieldLabel>
            <FieldDescription>
              Deleted every night, for everyone. Runs, approvals, usage and files stay, and so does each chat&apos;s summary.
            </FieldDescription>
          </FieldContent>
          <div>
            <Select value={retentionValue(retention ? retention.days : org.historyRetentionDays)} onValueChange={pick} disabled={!canEdit}>
              <SelectTrigger id="history-retention" className="w-full @md/field-group:w-36"><SelectValue /></SelectTrigger>
              <SelectContent>
                {RETENTION_CHOICES.map((c) => <SelectItem key={retentionValue(c.days)} value={retentionValue(c.days)}>{c.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </Field>
      </FieldGroup>
      {!canEdit && <p className="text-sm text-muted-foreground">Only owners and admins can change chat history.</p>}

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete messages older than {retentionLabel(asking)}?</AlertDialogTitle>
            <AlertDialogDescription>
              Every night, messages older than {retentionLabel(asking)} are deleted for everyone in {org.name}, in
              every chat. This can&apos;t be undone. Runs, approvals, usage and files stay, and so does each chat&apos;s summary.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep messages</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => void saveRetention(asking)}>Delete older messages</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
