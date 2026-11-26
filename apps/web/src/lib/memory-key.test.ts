import { describe, expect, it } from "vitest";
import { memoryKeyProblem, memoryKeyProviderName } from "./memory-key";

describe("memoryKeyProblem", () => {
  it("always needs a key, named after the provider", () => {
    expect(memoryKeyProblem("openai", "  ")).toBe("Paste your OpenAI API key.");
    expect(memoryKeyProblem("gemini", "")).toBe("Paste your Google Gemini API key.");
  });

  it("says so when a pasted key is too short or too long to be one", () => {
    expect(memoryKeyProblem("openai", "sk-123")).toBe("That key looks too short. Paste the whole key.");
    expect(memoryKeyProblem("openai", "x".repeat(401))).toBe("That's too long for an API key. Paste only the key.");
    expect(memoryKeyProblem("gemini", " AIza12345678 ")).toBeUndefined();
  });
});

describe("memoryKeyProviderName", () => {
  it("names each provider", () => {
    expect(memoryKeyProviderName("openai")).toBe("OpenAI");
    expect(memoryKeyProviderName("gemini")).toBe("Google Gemini");
  });
});
