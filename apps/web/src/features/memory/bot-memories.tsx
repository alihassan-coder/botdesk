import { useEffect, useState } from "react";
import { BrainCircuit, Search } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Skeleton } from "@/components/ui/skeleton";
import { actions, useCurrentUser, useMemoryList, useMemoryStatus } from "@/data/store";
import type { Bot } from "@/data/types";
import { canChangeMemory, canForgetEverything } from "@/lib/memory";
import { ForgetAllButton } from "./forget-all-button";
import { MemoryRow } from "./memory-row";

const SEARCH_DELAY_MS = 300;

/**
 * Everything one bot remembers that you may see: search it, correct it, forget it.
 * Used by Settings → Memory and the Memory tab in a bot's details (`compact`).
 */
export function BotMemories({ bot, compact = false }: { bot: Bot; compact?: boolean }) {
  const status = useMemoryStatus();
  const list = useMemoryList(bot.id);
  const role = useCurrentUser().role;
  const [query, setQuery] = useState("");

  useEffect(() => void actions.loadMemoryStatus(), []);

  // Typing searches after a short pause, so every key press isn't a request.
  useEffect(() => {
    const timer = setTimeout(() => void actions.loadMemories(bot.id, query.trim()), query ? SEARCH_DELAY_MS : 0);
    return () => clearTimeout(timer);
  }, [bot.id, query]);

  if (status && !status.enabled) {
    return (
      <Alert>
        <BrainCircuit />
        <AlertTitle>Memory is off</AlertTitle>
        <AlertDescription>{status.reason ?? "Bots on this server don't remember anything between chats."}</AlertDescription>
      </Alert>
    );
  }

  const items = list?.items ?? [];
  const searching = query.trim() !== "";

  return (
    <div className="flex flex-col gap-3">
      {!bot.memoryEnabled && (
        <p className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
          {bot.name} isn&apos;t learning anything new right now. Turn memory back on in Edit.
        </p>
      )}
      <div className="flex items-center gap-2">
        <InputGroup className="flex-1">
          <InputGroupAddon><Search /></InputGroupAddon>
          <InputGroupInput type="search" value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="Search memories" aria-label={`Search what ${bot.name} remembers`} />
        </InputGroup>
        {!compact && canForgetEverything(role) && <ForgetAllButton bot={bot} disabled={items.length === 0 && !searching} />}
      </div>

      {!list || (list.status === "loading" && items.length === 0) ? (
        <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading memories">
          <Skeleton className="h-16 rounded-xl" />
          <Skeleton className="h-16 rounded-xl" />
        </div>
      ) : list.status === "error" ? (
        <p role="alert" className="py-6 text-center text-sm text-destructive">{list.error}</p>
      ) : items.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          {searching ? `Nothing ${bot.name} remembers matches “${query.trim()}”.` : `${bot.name} hasn't remembered anything yet. It learns as you chat.`}
        </p>
      ) : (
        <ul className="flex flex-col gap-2" aria-label={`What ${bot.name} remembers`}>
          {items.map((m) => <MemoryRow key={m.id} memory={m} canChange={canChangeMemory(role, m)} />)}
        </ul>
      )}

      {compact && canForgetEverything(role) && items.length > 0 && !searching && (
        <div className="flex justify-end"><ForgetAllButton bot={bot} /></div>
      )}
    </div>
  );
}
