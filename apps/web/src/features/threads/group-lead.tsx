import { useId, useTransition } from "react";
import { toast } from "sonner";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { actions, useBots, useCanChangeLead } from "@/data/store";
import type { Thread } from "@/data/types";

const NO_LEAD = "";

/**
 * A group's lead: the bot that answers messages that don't @mention a bot (ADR 0009). Its
 * creator, owners and admins can pick another of the group's bots, or none; everyone else sees who it is.
 */
export function GroupLead({ thread }: { thread: Thread }) {
  const selectId = useId();
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
        {canChange ? <label htmlFor={selectId}>Lead</label> : "Lead"}
      </h3>
      {canChange ? (
        <NativeSelect id={selectId} className="w-full" value={lead?.id ?? NO_LEAD} disabled={saving} onChange={(e) => change(e.target.value)}>
          {bots.map((b) => (
            <NativeSelectOption key={b.id} value={b.id}>{b.name}</NativeSelectOption>
          ))}
          <NativeSelectOption value={NO_LEAD}>No lead</NativeSelectOption>
        </NativeSelect>
      ) : (
        <p className="text-sm font-medium">{lead?.name ?? "No lead"}</p>
      )}
      <p className="mt-1 text-xs text-muted-foreground">
        {lead ? `${lead.name} answers messages that don't @mention a bot.` : "Only the bots you @mention reply."}
      </p>
    </section>
  );
}
