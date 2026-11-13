import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Pencil, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { TimeAgo } from "@/components/time-ago";
import { actions } from "@/data/store";
import type { MemoryItem } from "@/data/types";

const SCOPE_LABEL: Record<MemoryItem["scope"], string> = { you: "From your chat", bot: "From group chats" };
const SCOPE_HINT: Record<MemoryItem["scope"], string> = {
  you: "Learned in your DM. Only used when you talk to this bot.",
  bot: "Learned in group chats. Used in everyone's chats with this bot.",
};

/** One memory. People allowed to change it can correct the wording or forget it. */
export function MemoryRow({ memory, canChange }: { memory: MemoryItem; canChange: boolean }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(memory.text);
  const [busy, startBusy] = useTransition();
  const when = memory.updatedAt ?? memory.createdAt;

  const forget = () =>
    startBusy(async () => {
      const result = await actions.forgetMemory(memory.botId, memory.id);
      if (!result.ok) toast.error(result.error);
      else toast.success("Forgotten");
    });

  const save = () =>
    startBusy(async () => {
      const result = await actions.correctMemory(memory.botId, memory.id, draft.trim());
      if (!result.ok) return void toast.error(result.error);
      setEditing(false);
      toast.success("Memory corrected");
    });

  if (editing) {
    return (
      <li className="flex flex-col gap-2 rounded-xl border p-3">
        <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={2} maxLength={2000}
          aria-label="What the bot should remember" autoFocus />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => { setDraft(memory.text); setEditing(false); }}>Cancel</Button>
          <Button size="sm" onClick={save} disabled={busy || !draft.trim() || draft.trim() === memory.text}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
      </li>
    );
  }

  return (
    <li className="flex items-start gap-2 rounded-xl border p-3">
      <div className="min-w-0 flex-1">
        <p className="text-sm text-pretty">{memory.text}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant={memory.scope === "you" ? "secondary" : "outline"} title={SCOPE_HINT[memory.scope]}>
            {SCOPE_LABEL[memory.scope]}
          </Badge>
          {when && <span>{memory.updatedAt ? "Corrected" : "Saved"} <TimeAgo iso={when} /></span>}
        </div>
      </div>
      {canChange && (
        <div className="flex shrink-0">
          <Button variant="ghost" size="icon-sm" onClick={() => setEditing(true)} disabled={busy} aria-label={`Correct: ${memory.text}`}>
            <Pencil />
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={forget} disabled={busy} aria-label={`Forget: ${memory.text}`}>
            <Trash2 />
          </Button>
        </div>
      )}
    </li>
  );
}
