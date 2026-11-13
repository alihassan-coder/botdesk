import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot as state } from "./store";

/*
 * Models & keys when NEXT_PUBLIC_API_URL is set. fetch is faked per route ("METHOD path"),
 * so these never touch a network.
 */

const org = { id: "o1", name: "Zara's team", slug: "zara-team", role: "owner" };
const me = { user: { id: "u1", name: "Zara", email: "zara@example.com", handle: "zara" }, organizations: [org] };
const notConnected = { source: null, keyHint: null, status: null, lastVerifiedAt: null, baseUrl: null };
const openai = { id: "openai", kind: "openai", name: "OpenAI", hint: "GPT models.", connected: false, ...notConnected };
const groq = { id: "groq", kind: "groq", name: "Groq", hint: "Fast.", connected: false, ...notConnected };
const connectedOpenai = { ...openai, connected: true, source: "org", keyHint: "abcd", status: "ok", lastVerifiedAt: "2026-11-13T10:00:00Z" };
const gpt = { id: "openai:gpt-5.5", provider: "openai", name: "gpt-5.5", contextWindow: null, pricing: null };

type Route = { status: number; body?: unknown };
let routes: Record<string, Route>;
let sent: { key: string; body: unknown }[];

beforeEach(async () => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  sent = [];
  routes = {
    "POST /api/v1/auth/sign-in": { status: 200, body: me },
    "GET /api/v1/orgs/o1/providers": { status: 200, body: [openai, groq] },
    "GET /api/v1/orgs/o1/models": { status: 200, body: { models: [], errors: [] } },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url.replace("http://api.test", "")}`;
      sent.push({ key, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const route = routes[key] ?? { status: 404, body: { detail: "Not found" } };
      return route.body === undefined ? new Response(null, { status: route.status }) : Response.json(route.body, { status: route.status });
    }),
  );
  await actions.signIn("zara@example.com", "long-enough");
  await vi.waitFor(() => expect(state().modelsLoading).toBe(false));
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("Models & keys on the API", () => {
  it("entering the org loads its providers and models instead of the demo's", () => {
    expect(state().modelProviders.map((p) => p.id)).toEqual(["openai", "groq"]);
    expect(state().models).toEqual([]);
  });

  it("saveProviderKey sends the key once, keeps only the hint, and reloads the models", async () => {
    routes["PUT /api/v1/orgs/o1/providers/openai"] = { status: 200, body: connectedOpenai };
    routes["GET /api/v1/orgs/o1/providers"] = { status: 200, body: [connectedOpenai, groq] };
    routes["GET /api/v1/orgs/o1/models"] = { status: 200, body: { models: [gpt], errors: [] } };

    await expect(actions.saveProviderKey("openai", { apiKey: "sk-proj-1234567890abcd" })).resolves.toEqual({ ok: true });
    expect(sent.find((s) => s.key === "PUT /api/v1/orgs/o1/providers/openai")?.body).toEqual({ apiKey: "sk-proj-1234567890abcd" });
    expect(state().modelProviders[0]).toMatchObject({ connected: true, keyHint: "abcd" });
    expect(JSON.stringify(state())).not.toContain("1234567890");
    await vi.waitFor(() => expect(state().models.map((m) => m.id)).toEqual(["openai:gpt-5.5"]));
  });

  it("saveProviderKey shows why a key didn't work", async () => {
    const detail = "That key didn't work: 401: Incorrect API key provided: [key]";
    routes["PUT /api/v1/orgs/o1/providers/groq"] = { status: 400, body: { detail } };
    await expect(actions.saveProviderKey("groq", { apiKey: "gsk_wrong" })).resolves.toEqual({ ok: false, error: detail });
    expect(state().modelProviders[1].connected).toBe(false);
  });

  it("a provider that is down is reported next to the models of the others", async () => {
    routes["GET /api/v1/orgs/o1/models?refresh=true"] = {
      status: 200, body: { models: [gpt], errors: [{ provider: "groq", message: "Groq: 503: Service unavailable" }] },
    };
    await actions.loadModels({ refresh: true });
    expect(state().models.map((m) => m.id)).toEqual(["openai:gpt-5.5"]);
    expect(state().modelProblems).toEqual([{ provider: "groq", message: "Groq: 503: Service unavailable" }]);
  });

  it("testProviderKey records the result and passes on the reason it failed", async () => {
    const invalid = { ...connectedOpenai, status: "invalid" };
    routes["POST /api/v1/orgs/o1/providers/openai/test"] = { status: 200, body: { ok: false, error: "That key didn't work: 401", provider: invalid } };
    await expect(actions.testProviderKey("openai")).resolves.toEqual({ ok: false, error: "That key didn't work: 401" });
    expect(state().modelProviders[0].status).toBe("invalid");
  });

  it("removeProviderKey disconnects it, then asks the API again (a server key may take over)", async () => {
    routes["DELETE /api/v1/orgs/o1/providers/openai"] = { status: 204 };
    await expect(actions.removeProviderKey("openai")).resolves.toEqual({ ok: true });
    expect(state().modelProviders[0].connected).toBe(false);
    await vi.waitFor(() => expect(sent.filter((s) => s.key === "GET /api/v1/orgs/o1/providers")).toHaveLength(2));
  });
});
