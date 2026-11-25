import { useMemo } from "react";
import { useBots, useCurrentUser, useUsers } from "@/data/store";
import type { Thread } from "@/data/types";
import type { MentionOption } from "./mention-suggestions";

/**
 * Who the @ list offers, bots first. A group: its bots and people (not you). A DM: its bot and
 * every other bot of the organization, which a mention pulls in as a guest for one reply (ADR 0009).
 */
export function useMentionOptions(thread: Thread): MentionOption[] {
  const bots = useBots();
  const users = useUsers();
  const me = useCurrentUser();
  return useMemo(() => {
    const inChat = (type: "bot" | "user", id: string) => thread.participants.some((p) => p.type === type && p.id === id);
    const isDm = thread.kind === "dm";
    const botOptions: MentionOption[] = bots
      .filter((b) => isDm || inChat("bot", b.id))
      .toSorted((a, b) => Number(b.id === thread.botId) - Number(a.id === thread.botId))
      .map((b) => ({
        type: "bot", id: b.id, handle: b.handle, name: b.name, role: b.role, color: b.avatarColor, status: b.status,
        ...(isDm && b.id !== thread.botId ? { hint: "Joins as a guest" } : {}),
      }));
    const userOptions: MentionOption[] = users
      .filter((u) => u.id !== me?.id && inChat("user", u.id))
      .map((u) => ({ type: "user", id: u.id, handle: u.handle, name: u.name }));
    return [...botOptions, ...userOptions];
  }, [bots, users, me?.id, thread.participants, thread.kind, thread.botId]);
}
