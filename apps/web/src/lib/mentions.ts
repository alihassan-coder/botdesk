import type { Participant } from "@/data/types";

/** Anything that can be @mentioned: it has an id and a handle. */
interface Mentionable {
  id: string;
  handle: string;
}

const MENTION = /@([a-z0-9_-]+)/gi;

/**
 * Finds the bots and members a message mentions, in the order they appear.
 * Unknown handles are ignored and each participant is listed once.
 * Bots win over members if both use the same handle.
 */
export function parseMentions(text: string, bots: Mentionable[], users: Mentionable[]): Participant[] {
  const found: Participant[] = [];

  for (const [, rawHandle] of text.matchAll(MENTION)) {
    const handle = rawHandle.toLowerCase();
    const bot = bots.find((b) => b.handle === handle);
    const user = bot ? undefined : users.find((u) => u.handle === handle);
    const participant: Participant | null = bot ? { type: "bot", id: bot.id } : user ? { type: "user", id: user.id } : null;

    if (participant && !found.some((p) => p.type === participant.type && p.id === participant.id)) {
      found.push(participant);
    }
  }

  return found;
}
