import { describe, expect, it } from "vitest";
import { canChangeMemory, canForgetEverything } from "./memory";

describe("memory permissions", () => {
  it("owners and admins change any memory; members only their own DM ones", () => {
    expect(canChangeMemory("owner", { scope: "bot" })).toBe(true);
    expect(canChangeMemory("admin", { scope: "bot" })).toBe(true);
    expect(canChangeMemory("member", { scope: "you" })).toBe(true);
    expect(canChangeMemory("member", { scope: "bot" })).toBe(false);
  });

  it("only owners and admins make a bot forget everything", () => {
    expect([canForgetEverything("owner"), canForgetEverything("admin"), canForgetEverything("member")]).toEqual([true, true, false]);
  });
});
