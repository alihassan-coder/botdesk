import { describe, expect, it } from "vitest";
import { routeMessage, type ChatBots } from "./mention-routing";

const ORG_BOTS = ["chief", "scout", "reader", "writer"].map((handle) => ({ id: `b_${handle}`, handle }));
const GROUP: ChatBots = { kind: "group", bots: ["b_chief", "b_scout", "b_reader"], defaultBot: "b_chief" };
const NO_LEAD: ChatBots = { ...GROUP, defaultBot: undefined };
const DM: ChatBots = { kind: "dm", bots: ["b_chief", "b_reader"], defaultBot: "b_chief" };
const LIMIT = 3;

const who = (routing: ReturnType<typeof routeMessage>) => routing.replies.map((r) => [r.botId.slice(2), r.hop, r.reason]);

describe("routeMessage: a member's message (same rules as the API's mention_routing)", () => {
  it.each([
    ["group: no mention goes to the lead", GROUP, "what's new?", [["chief", 0, "lead"]]],
    ["group: no mention and no lead: nobody", NO_LEAD, "what's new?", []],
    ["group: mentions in mention order", GROUP, "@reader then @scout", [["reader", 0, "mention"], ["scout", 0, "mention"]]],
    ["group: duplicate mentions reply once", GROUP, "@scout @Scout", [["scout", 0, "mention"]]],
    ["group: an email address is not a mention", GROUP, "mail scout@acme.dev", [["chief", 0, "lead"]]],
    ["group: a bot outside the chat is ignored", GROUP, "@writer help", [["chief", 0, "lead"]]],
    ["dm: no mention: the DM's bot", DM, "hello", [["chief", 0, "dm_bot"]]],
    ["dm: another org bot joins as a guest", DM, "@writer draft it", [["writer", 0, "guest"]]],
    ["dm: the DM's bot replies too when mentioned", DM, "@writer and @chief", [["writer", 0, "guest"], ["chief", 0, "dm_bot"]]],
  ] as const)("%s", (_name, chat, text, expected) => {
    const routing = routeMessage(chat, text, { orgBots: ORG_BOTS, hopLimit: LIMIT });
    expect(who(routing)).toEqual(expected);
    expect(routing.chainStopped).toBe(false);
  });
});

describe("routeMessage: a bot's reply", () => {
  it.each([
    ["group: no mention: nobody", GROUP, "b_scout", 0, "done", [], false],
    ["group: a mention starts a run one hop on", GROUP, "b_chief", 0, "@scout look", [["scout", 1, "mention"]], false],
    ["group: a bot never triggers itself", GROUP, "b_scout", 0, "@scout @reader", [["reader", 1, "mention"]], false],
    ["group: a bot outside the chat is ignored", GROUP, "b_chief", 0, "@writer", [], false],
    ["group: the last allowed hop", GROUP, "b_chief", LIMIT - 1, "@scout", [["scout", LIMIT, "mention"]], false],
    ["group: past the hop limit: stopped", GROUP, "b_chief", LIMIT, "@scout", [], true],
    ["group: at the limit with no mention: not a stop", GROUP, "b_chief", LIMIT, "done", [], false],
    ["dm: the guest hands back to the DM's bot", DM, "b_reader", 0, "@chief over to you", [["chief", 1, "mention"]], false],
    ["dm: a bot can't pull a new bot in", DM, "b_chief", 0, "@writer help", [], false],
  ] as const)("%s", (_name, chat, botId, hop, text, expected, stopped) => {
    const routing = routeMessage(chat, text, { orgBots: ORG_BOTS, hopLimit: LIMIT, byBot: { botId, hop } });
    expect(who(routing)).toEqual(expected);
    expect(routing.chainStopped).toBe(stopped);
  });
});
