import { describe, expect, it } from "vitest";
import { makeHandle } from "./handle";

describe("makeHandle", () => {
  it("lowercases and joins words with dashes", () => {
    expect(makeHandle("Inbox Zero", [])).toBe("inbox-zero");
  });

  it("drops symbols and accents", () => {
    expect(makeHandle("  Café & Ops! ", [])).toBe("cafe-ops");
  });

  it("adds a number when the handle is taken", () => {
    expect(makeHandle("Chief", ["chief"])).toBe("chief-2");
    expect(makeHandle("Chief", ["chief", "chief-2"])).toBe("chief-3");
  });

  it("falls back to 'bot' for names with no letters", () => {
    expect(makeHandle("!!!", [])).toBe("bot");
  });
});
