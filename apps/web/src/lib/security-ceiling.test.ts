import { describe, expect, it } from "vitest";
import { looserThan, strictestLevel } from "./security-ceiling";

describe("strictestLevel", () => {
  it("is the strictest of the levels given (the organization's ceiling caps a bot)", () => {
    expect(strictestLevel("autonomous", "read-only")).toBe("read-only");
    expect(strictestLevel("ask-before-acting", "autonomous")).toBe("ask-before-acting");
    expect(strictestLevel("autonomous", "autonomous")).toBe("autonomous");
  });
});

describe("looserThan", () => {
  it("is true only for a level that lets the bot do more than the ceiling", () => {
    expect(looserThan("autonomous", "ask-before-acting")).toBe(true);
    expect(looserThan("ask-before-acting", "read-only")).toBe(true);
    expect(looserThan("read-only", "autonomous")).toBe(false);
    expect(looserThan("ask-before-acting", "ask-before-acting")).toBe(false);
  });
});
