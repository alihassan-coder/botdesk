import { describe, expect, it } from "vitest";
import { parseMentions, splitMentions } from "./mentions";

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

  it("ignores the @ inside an email address", () => {
    expect(parseMentions("email sara@inbox.dev, then @sales", bots, users)).toEqual([{ type: "bot", id: "b_sales" }]);
  });
});

describe("splitMentions", () => {
  it("splits @handles out of the text", () => {
    expect(splitMentions("ask @inbox now")).toEqual([
      { text: "ask ", isMention: false },
      { text: "@inbox", isMention: true },
      { text: " now", isMention: false },
    ]);
  });

  it("keeps an email address in one plain piece", () => {
    expect(splitMentions("to=sara@acme.dev")).toEqual([{ text: "to=sara@acme.dev", isMention: false }]);
  });

  it("finds a handle at the start, after punctuation, and in brackets", () => {
    expect(splitMentions("@sara, (@inbox)").filter((p) => p.isMention).map((p) => p.text)).toEqual(["@sara", "@inbox"]);
  });

  it("returns no pieces for empty text", () => {
    expect(splitMentions("")).toEqual([]);
  });
});
