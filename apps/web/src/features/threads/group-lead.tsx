import { useId, useTransition } from "react";
import { toast } from "sonner";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { actions, useBots, useCanChangeLead } from "@/data/store";
import type { Thread } from "@/data/types";

/** Radix Select can't hold an empty value, so "No lead" has a name of its own (bot ids never look like it). */
const NO_LEAD = "none";

/**
 * A group's lead: the bot that answers messages that don't @mention a bot (ADR 0009). Its
 * creator, owners and admins can pick another of the group's bots, or none; everyone else sees who it is.
 */
export function GroupLead({ thread }: { thread: Thread }) {
  const triggerId = useId();
  const canChange = useCanChangeLead(thread);
  const allBots = useBots();
  const bots = allBots.filter((b) => thread.participants.some((p) => p.type === "bot" && p.id === b.id));
  const lead = bots.find((b) => b.id === thread.leadBotId);
  const [saving, startSaving] = useTransition();

  function change(botId: string) {
    startSaving(async () => {
      const result = await actions.setGroupLead(thread.id, botId === NO_LEAD ? null : botId);
      if (!result.ok) toast.error(result.error);
    });
  }

  return (
    <section>
      <h3 className="mb-1 text-xs font-medium text-muted-foreground">
        {canChange ? <label htmlFor={triggerId}>Lead</label> : "Lead"}
      </h3>
      {canChange ? (
        <Select value={lead?.id ?? NO_LEAD} onValueChange={change} disabled={saving}>
          <SelectTrigger id={triggerId} className="w-full"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_LEAD}>No lead</SelectItem>
            {bots.map((b) => <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>)}
          </SelectContent>
        </Select>
      ) : (
        <p className="text-sm font-medium">{lead?.name ?? "No lead"}</p>
      )}
      <p className="mt-1 text-xs text-muted-foreground">
        {lead ? `${lead.name} answers messages that don't @mention a bot.` : "Only the bots you @mention reply."}
      </p>
    </section>
  );
}
