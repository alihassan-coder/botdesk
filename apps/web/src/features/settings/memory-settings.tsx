"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TimeAgo } from "@/components/time-ago";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { actions, useBots, useMemories } from "@/data/store";
import { SettingsSection } from "./settings-shell";

const EVERYONE = "shared";

/** Settings → Memory: everything your bots remember, which bot it belongs to, and forget. */
export function MemorySettings() {
  const memories = useMemories();
  const bots = useBots();
  const [filter, setFilter] = useState("all");

  const shown = memories.filter((m) => filter === "all" || (filter === EVERYONE ? !m.botId : m.botId === filter));
  const ownerName = (botId?: string) => (botId ? (bots.find((b) => b.id === botId)?.name ?? "A bot") : "All bots");

  return (
    <SettingsSection
      title="Memory"
      description="Facts your bots have learned. Shared memories are used by every bot. Forget anything that's wrong."
      action={
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="w-44" aria-label="Show memories for"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Everything</SelectItem>
            <SelectItem value={EVERYONE}>Shared with all bots</SelectItem>
            {bots.map((b) => <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>)}
          </SelectContent>
        </Select>
      }
    >
      {shown.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">Nothing remembered here yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {shown.map((m) => (
            <li key={m.id} className="flex items-start gap-3 rounded-2xl border p-4">
              <div className="min-w-0 flex-1">
                <p className="text-sm">{m.text}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {ownerName(m.botId)} · {m.source} · <TimeAgo iso={m.createdAt} />
                </p>
              </div>
              <Button variant="ghost" size="icon-sm" onClick={() => actions.deleteMemory(m.id)} aria-label={`Forget: ${m.text}`}>
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </SettingsSection>
  );
}
