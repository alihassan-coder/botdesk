import { describe, expect, it } from "vitest";
import { browserKeyProblem } from "./browser-providers";

const steel = { provider: "steel" as const, keyHint: "abcd", projectId: "", localAvailable: true };

describe("browserKeyProblem", () => {
  it("needs no key for Local, and a key for a new cloud provider", () => {
    expect(browserKeyProblem("local", "")).toBeUndefined();
    expect(browserKeyProblem("kernel", "", steel)).toBe("Paste your Kernel API key.");
  });

  it("keeps the saved key when the provider stays the same", () => {
    expect(browserKeyProblem("steel", "  ", steel)).toBeUndefined();
  });

  it("says so when a pasted key is too short to be one", () => {
    expect(browserKeyProblem("steel", "abc")).toBe("That key looks too short. Paste the whole key.");
    expect(browserKeyProblem("steel", "ste_1234567890")).toBeUndefined();
  });
});
