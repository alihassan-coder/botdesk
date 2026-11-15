import { parseMentions } from "./mentions";

/**
 * Mention routing (ADR 0009), the demo's copy of the API's `services/mention_routing.py`:
 * which bots answer a message, at what hop, and whether a chain of bot replies stopped.
 *
 * - A member's message in a group: the bots in it they @mention, in order; none mentioned: the lead.
 * - A member's message in a DM: the DM's bot; @mentioning other bots of the org pulls each in
 *   as a guest for one reply (the DM's bot then answers only if mentioned too).
 * - A bot's reply: the bots it @mentions that are already in the chat, never itself, one hop on.
 *   Past the hop limit nothing starts and `chainStopped` says so.
 */

export const HOP_LIMIT = 3;
export const chainStoppedText = (hopLimit: number) => `Stopped a chain of bot replies after ${hopLimit} hops.`;

export interface ChatBots {
  kind: "dm" | "group";
  /** Bots another bot may mention here: a group's bots; a DM's own bot and its guests so far. */
  bots: readonly string[];
  /** Who answers a member's message that mentions no bot: a group's lead, a DM's own bot. */
  defaultBot?: string;
}

export interface BotReply {
  botId: string;
  hop: number;
  reason: "mention" | "lead" | "dm_bot" | "guest";
}

export interface Routing {
  replies: BotReply[];
  chainStopped: boolean;
}

export function routeMessage(
  chat: ChatBots,
  text: string,
  { orgBots, hopLimit, byBot }: { orgBots: { id: string; handle: string }[]; hopLimit: number; byBot?: { botId: string; hop: number } },
): Routing {
  const mentioned = parseMentions(text, orgBots, []).map((p) => p.id);
  if (byBot) {
    const targets = mentioned.filter((id) => chat.bots.includes(id) && id !== byBot.botId);
    if (targets.length === 0) return { replies: [], chainStopped: false };
    const hop = byBot.hop + 1;
    if (hop > hopLimit) return { replies: [], chainStopped: true };
    return { replies: targets.map((botId) => ({ botId, hop, reason: "mention" })), chainStopped: false };
  }
  if (chat.kind === "dm") {
    if (mentioned.length === 0) return only(chat.defaultBot, "dm_bot");
    return { replies: mentioned.map((botId) => ({ botId, hop: 0, reason: botId === chat.defaultBot ? "dm_bot" : "guest" })), chainStopped: false };
  }
  const inChat = mentioned.filter((id) => chat.bots.includes(id));
  if (inChat.length === 0) return only(chat.defaultBot && chat.bots.includes(chat.defaultBot) ? chat.defaultBot : undefined, "lead");
  return { replies: inChat.map((botId) => ({ botId, hop: 0, reason: "mention" })), chainStopped: false };
}

function only(botId: string | undefined, reason: BotReply["reason"]): Routing {
  return { replies: botId ? [{ botId, hop: 0, reason }] : [], chainStopped: false };
}
