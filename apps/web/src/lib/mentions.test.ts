import { describe, expect, it } from "vitest";
import { parseMentions } from "./mentions";

const bots = [
  { id: "b_inbox", handle: "inbox" },
  { id: "b_sales", handle: "sales" },
];
const users = [
  { id: "u_sara", handle: "sara" },
  { id: "u_clash", handle: "sales" },
];

describe("parseMentions", () => {
  it("finds bots and members in order", () => {
    expect(parseMentions("@sara ask @inbox to check", bots, users)).toEqual([
      { type: "user", id: "u_sara" },
      { type: "bot", id: "b_inbox" },
    ]);
  });

  it("ignores case and unknown handles", () => {
    expect(parseMentions("@INBOX and @nobody", bots, users)).toEqual([{ type: "bot", id: "b_inbox" }]);
  });

  it("lists each participant once", () => {
    expect(parseMentions("@inbox @inbox", bots, users)).toHaveLength(1);
  });

  it("prefers the bot when a member shares its handle", () => {
    expect(parseMentions("@sales", bots, users)).toEqual([{ type: "bot", id: "b_sales" }]);
  });

  it("returns nothing when there are no mentions", () => {
    expect(parseMentions("no mentions here", bots, users)).toEqual([]);
  });
});
