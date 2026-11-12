import { describe, expect, it } from "vitest";
import { looksLikeEmail } from "./email";

describe("looksLikeEmail", () => {
  it("accepts ordinary addresses, even with spaces around them", () => {
    expect(looksLikeEmail("ali@acme.dev")).toBe(true);
    expect(looksLikeEmail(" ali@acme.dev ")).toBe(true);
  });

  it("rejects text that can't be an address", () => {
    expect(looksLikeEmail("ali")).toBe(false);
    expect(looksLikeEmail("ali@acme")).toBe(false);
    expect(looksLikeEmail("a li@acme.dev")).toBe(false);
  });
});
