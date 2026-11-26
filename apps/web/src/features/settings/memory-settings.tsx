"use client";

import { useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useBots, useBotsLoading } from "@/data/store";
import { BotMemories } from "@/features/memory/bot-memories";
import { MemoryKeyCard } from "./memory-key-card";
import { SettingsSection } from "./settings-shell";

/** Settings → Memory: pick a bot to see what it remembers, correct it, or make it forget; and the org's memory key. */
export function MemorySettings() {
  const bots = useBots();
  const loading = useBotsLoading();
  const [picked, setPicked] = useState<string>();
  const bot = bots.find((b) => b.id === picked) ?? bots[0];

  return (
    <div className="flex flex-col gap-8">
      <SettingsSection
        title="Memory"
        description="What your bots learned while chatting. Memories from group chats help everyone's chats with that bot; ones from your DM stay yours."
        action={
          bot && (
            <Select value={bot.id} onValueChange={setPicked}>
              <SelectTrigger className="w-44" aria-label="Show memories of"><SelectValue /></SelectTrigger>
              <SelectContent>
                {bots.map((b) => <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>)}
              </SelectContent>
            </Select>
          )
        }
      >
        {bot ? (
          <BotMemories key={bot.id} bot={bot} />
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {loading ? "Loading your bots…" : "Hire a bot first. What it learns will show up here."}
          </p>
        )}
      </SettingsSection>

      <SettingsSection
        title="Memory key"
        description="An OpenAI or Google Gemini key used only for bots' memory: remembering what they learn and recalling it later, never for replies. Without one, memory uses this server's own key, if whoever runs it set one up."
      >
        <MemoryKeyCard />
      </SettingsSection>
    </div>
  );
}
