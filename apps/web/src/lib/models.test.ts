import { describe, expect, it } from "vitest";
import type { Model, ModelProvider } from "@/data/types";
import { formatContextWindow, formatModelPrice, groupModels, maskedKey, modelMatches } from "./models";

const providers: ModelProvider[] = [
  { id: "anthropic", kind: "anthropic", name: "Anthropic", hint: "", connected: true },
  { id: "groq", kind: "groq", name: "Groq", hint: "", connected: false },
  { id: "custom-1", kind: "custom", name: "Ollama", hint: "", connected: true },
];
const opus: Model = { id: "anthropic:claude-opus-5-5", provider: "anthropic", name: "Claude Opus 5.5", contextWindow: 1_000_000 };
const llama: Model = { id: "custom-1:llama3.2:latest", provider: "custom-1", name: "llama3.2:latest" };
const grok: Model = {
  id: "openrouter:x-ai/grok-4.5", provider: "openrouter", name: "xAI: Grok 4.5", pricing: { inputPerMTok: 3, outputPerMTok: 15 },
};

describe("groupModels", () => {
  it("groups by provider in the providers' order, skipping providers without models", () => {
    expect(groupModels([llama, opus, grok], providers)).toEqual([
      { providerId: "anthropic", providerName: "Anthropic", models: [opus] },
      { providerId: "custom-1", providerName: "Ollama", models: [llama] },
      { providerId: "openrouter", providerName: "openrouter", models: [grok] },
    ]);
  });

  it("keeps only models matching every word, including the provider's name", () => {
    expect(groupModels([llama, opus, grok], providers, "ollama llama").map((g) => g.models)).toEqual([[llama]]);
    expect(groupModels([llama, opus, grok], providers, "nothing like this")).toEqual([]);
    expect(modelMatches(opus, "OPUS 5")).toBe(true);
  });
});

describe("model details", () => {
  it("prices per million tokens and context windows, when known", () => {
    expect(formatModelPrice(grok)).toBe("$3 / $15 per M tokens");
    expect(formatModelPrice({ ...grok, pricing: { inputPerMTok: 0.125, outputPerMTok: 0 } })).toBe("$0.13 / $0 per M tokens");
    expect(formatModelPrice(opus)).toBeUndefined();
    expect(formatContextWindow(opus)).toBe("1M context");
    expect(formatContextWindow(llama)).toBeUndefined();
  });

  it("shows only a key's last 4 characters", () => {
    expect(maskedKey("abcd")).toBe("••••abcd");
    expect(maskedKey()).toBe("No key shown");
  });
});
