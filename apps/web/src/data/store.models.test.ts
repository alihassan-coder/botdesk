import { describe, expect, it } from "vitest";
import { actions, getStoreSnapshot as state } from "./store";
import { toModel, toModelProvider } from "./api/map";

/* Models & keys in the demo (no API): keys "work" unless they start with "bad". */

const provider = (id: string) => state().modelProviders.find((p) => p.id === id);

describe("Models & keys in the demo", () => {
  it("saving a key connects the provider and keeps only its last 4 characters", async () => {
    expect(provider("groq")?.connected).toBe(false);
    await expect(actions.saveProviderKey("groq", { apiKey: "gsk_live_1234567890wxyz" })).resolves.toEqual({ ok: true });
    expect(provider("groq")).toMatchObject({ connected: true, source: "org", keyHint: "wxyz", status: "ok" });
    expect(JSON.stringify(state().modelProviders)).not.toContain("1234567890");
    expect(state().models.some((m) => m.id === "groq:llama-3.3-70b-versatile")).toBe(true);
  });

  it("a key that doesn't work is refused with the reason, and nothing changes", async () => {
    const result = await actions.saveProviderKey("groq", { apiKey: "bad-key-000000000" });
    expect(result).toEqual({ ok: false, error: "That key didn't work: 401: Incorrect API key provided." });
    expect(provider("groq")?.connected).toBe(false);
  });

  it("a custom server gets its own id, name and base URL", async () => {
    await actions.saveProviderKey("custom", { apiKey: "", label: "Ollama", baseUrl: "http://localhost:11434/v1/" });
    const added = state().modelProviders.at(-1)!;
    expect(added).toMatchObject({ kind: "custom", name: "Ollama", baseUrl: "http://localhost:11434/v1", connected: true });
    expect(added.id).toMatch(/^custom-/);
    expect(added.keyHint).toBeUndefined();
  });

  it("removing a key disconnects a built-in provider, takes its models, and drops a custom server", async () => {
    await actions.removeProviderKey("anthropic");
    expect(provider("anthropic")).toEqual(expect.objectContaining({ connected: false }));
    expect(provider("anthropic")?.keyHint).toBeUndefined();
    expect(state().models.some((m) => m.provider === "anthropic")).toBe(false);

    await actions.removeProviderKey("custom-gpu-box");
    expect(provider("custom-gpu-box")).toBeUndefined();
  });

  it("testing a key records when it was checked", async () => {
    await expect(actions.testProviderKey("openai")).resolves.toEqual({ ok: true });
    expect(provider("openai")?.status).toBe("ok");
  });
});

describe("API → web shapes for models", () => {
  it("leaves out what the API doesn't know, and reads SQLite times as UTC", () => {
    expect(toModelProvider({
      id: "groq", kind: "groq", name: "Groq", hint: "Fast.", connected: false, source: null, keyHint: null, status: null, lastVerifiedAt: null, baseUrl: null,
    })).toEqual({ id: "groq", kind: "groq", name: "Groq", hint: "Fast.", connected: false });
    expect(toModelProvider({
      id: "openai", kind: "openai", name: "OpenAI", hint: "", connected: true, source: "org", keyHint: "abcd", status: "ok",
      lastVerifiedAt: "2026-11-13T10:00:00", baseUrl: null,
    })).toMatchObject({ source: "org", keyHint: "abcd", status: "ok", lastVerifiedAt: "2026-11-13T10:00:00Z" });
  });

  it("a model keeps its context window and prices per million tokens", () => {
    expect(toModel({ id: "openrouter:x-ai/grok-4.5", provider: "openrouter", name: "Grok 4.5", contextWindow: 256000, pricing: { inputPerMtok: 3, outputPerMtok: 15 } }))
      .toEqual({ id: "openrouter:x-ai/grok-4.5", provider: "openrouter", name: "Grok 4.5", contextWindow: 256000, pricing: { inputPerMTok: 3, outputPerMTok: 15 } });
    expect(toModel({ id: "openai:gpt-5.5", provider: "openai", name: "gpt-5.5", contextWindow: null, pricing: null }))
      .toEqual({ id: "openai:gpt-5.5", provider: "openai", name: "gpt-5.5" });
  });
});
