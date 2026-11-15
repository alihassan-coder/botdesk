import { describe, expect, it } from "vitest";
import { activeMention, insertMention, parseMentions, rankMentionables, splitMentions } from "./mentions";

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

describe("activeMention", () => {
  it("finds the @word the caret is in", () => {
    expect(activeMention("hi @sa", 6)).toEqual({ start: 3, query: "sa" });
  });
  it("opens on a bare @", () => {
    expect(activeMention("@", 1)).toEqual({ start: 0, query: "" });
  });
  it("works after an opening bracket", () => {
    expect(activeMention("(@in", 4)).toEqual({ start: 1, query: "in" });
  });
  it("ignores the @ in an email address", () => {
    expect(activeMention("mail sara@ac", 12)).toBeNull();
  });
  it("closes once a space follows the handle", () => {
    expect(activeMention("@sara hi", 8)).toBeNull();
  });
  it("only looks at the text before the caret", () => {
    expect(activeMention("@sales and more", 3)).toEqual({ start: 0, query: "sa" });
  });
});

describe("insertMention", () => {
  it("replaces the typed @word with the handle and a space", () => {
    expect(insertMention("hi @sa", { start: 3, query: "sa" }, 6, "sales")).toEqual({ text: "hi @sales ", caret: 10 });
  });
  it("keeps the text after the caret, without doubling the space", () => {
    expect(insertMention("@in please", { start: 0, query: "in" }, 3, "inbox")).toEqual({ text: "@inbox please", caret: 7 });
  });
});

describe("rankMentionables", () => {
  const people = [
    { id: "1", handle: "sales", name: "Sales Outbound" },
    { id: "2", handle: "inbox", name: "Inbox Manager" },
    { id: "3", handle: "sara", name: "Sara Khan" },
  ];
  it("lists everyone, in order, for an empty query", () => {
    expect(rankMentionables("", people).map((p) => p.id)).toEqual(["1", "2", "3"]);
  });
  it("puts handle prefix matches first, then name matches", () => {
    expect(rankMentionables("sa", people).map((p) => p.id)).toEqual(["1", "3"]);
    expect(rankMentionables("man", people).map((p) => p.id)).toEqual(["2"]);
  });
  it("ignores case", () => {
    expect(rankMentionables("IN", people).map((p) => p.id)).toEqual(["2"]);
  });
});
