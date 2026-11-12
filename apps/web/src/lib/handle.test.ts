import { describe, expect, it } from "vitest";
import { finishSlug, makeHandle, slugWhileTyping } from "./handle";

describe("makeHandle", () => {
  it("lowercases and joins words with dashes", () => {
    expect(makeHandle("Inbox Zero", [])).toBe("inbox-zero");
  });

  it("drops symbols and accents", () => {
    expect(makeHandle("  Café & Ops! ", [])).toBe("cafe-ops");
    expect(makeHandle("Renée Smith", [])).toBe("renee-smith");
  });

  it("adds a number when the handle is taken", () => {
    expect(makeHandle("Chief", ["chief"])).toBe("chief-2");
    expect(makeHandle("Chief", ["chief", "chief-2"])).toBe("chief-3");
  });

  it("falls back to 'bot' for names with no letters", () => {
    expect(makeHandle("!!!", [])).toBe("bot");
  });
});

describe("slugWhileTyping", () => {
  it("keeps a trailing dash so the next word can be typed", () => {
    expect(slugWhileTyping("my-")).toBe("my-");
    expect(slugWhileTyping("My Team")).toBe("my-team");
  });

  it("stays empty when cleared", () => {
    expect(slugWhileTyping("")).toBe("");
  });

  it("drops leading dashes and accents", () => {
    expect(slugWhileTyping("--Équipe")).toBe("equipe");
  });
});

describe("finishSlug", () => {
  it("trims the trailing dash before saving", () => {
    expect(finishSlug("my-team-")).toBe("my-team");
  });
});
