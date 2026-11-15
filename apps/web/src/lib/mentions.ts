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

/** The @word being typed: where its @ is, and the letters after it so far. */
export interface ActiveMention {
  start: number;
  query: string;
}

// Same rule as MENTION, anchored at the caret: an @ that starts a word, then handle letters.
const TYPING_MENTION = /(?<![\w.@])@([a-z0-9_-]*)$/i;

/** The @word the caret is at the end of, or null (so the suggestion list stays closed). */
export function activeMention(text: string, caret: number): ActiveMention | null {
  const match = TYPING_MENTION.exec(text.slice(0, caret));
  return match ? { start: match.index, query: match[1] } : null;
}

/** Replaces the typed @word with `@handle ` and says where the caret goes next. */
export function insertMention(
  text: string,
  mention: ActiveMention,
  caret: number,
  handle: string,
): { text: string; caret: number } {
  const after = text.slice(caret);
  const inserted = `@${handle}${after.startsWith(" ") ? "" : " "}`;
  const before = text.slice(0, mention.start) + inserted;
  return { text: before + after, caret: before.length + (after.startsWith(" ") ? 1 : 0) };
}

/**
 * Who matches what's typed after the @: handles that start with it first, then names
 * that contain it. An empty query keeps everyone in their original order.
 */
export function rankMentionables<T extends Mentionable & { name: string }>(query: string, items: T[]): T[] {
  const q = query.toLowerCase();
  if (!q) return items;
  const byHandle = items.filter((i) => i.handle.toLowerCase().startsWith(q));
  const byName = items.filter((i) => !byHandle.includes(i) && i.name.toLowerCase().includes(q));
  return [...byHandle, ...byName];
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
