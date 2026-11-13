import type { Participant } from "@/data/types";

/** Anything that can be @mentioned: it has an id and a handle. */
interface Mentionable {
  id: string;
  handle: string;
}

// An @handle starts a word: the @ in an email address (sara@acme.dev) is not a mention.
const MENTION = /(?<![\w.@])@([a-z0-9_-]+)/gi;

/** A piece of text, and whether it is an @handle. */
export interface TextPiece {
  text: string;
  isMention: boolean;
}

/** Splits text into plain pieces and @handles, in order, so a view can colour the handles. */
export function splitMentions(text: string): TextPiece[] {
  const pieces: TextPiece[] = [];
  let last = 0;
  for (const match of text.matchAll(MENTION)) {
    if (match.index > last) pieces.push({ text: text.slice(last, match.index), isMention: false });
    pieces.push({ text: match[0], isMention: true });
    last = match.index + match[0].length;
  }
  if (last < text.length) pieces.push({ text: text.slice(last), isMention: false });
  return pieces;
}

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
