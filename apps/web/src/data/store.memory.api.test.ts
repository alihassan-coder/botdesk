import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot as state } from "./store";

/*
 * Memory when NEXT_PUBLIC_API_URL is set. fetch is faked per route ("METHOD path"),
 * so these never touch a network.
 */

const org = { id: "o1", name: "Zara's team", slug: "zara-team", plan: "free", role: "member" };
const me = { user: { id: "u1", name: "Zara", email: "zara@example.com", handle: "zara" }, organizations: [org] };
const BOT = "/api/v1/orgs/o1/bots/b1/memories";
const fridays = { id: "m1", text: "Ships on Fridays", scope: "bot", createdAt: "2026-11-10T09:00:00+00:00", updatedAt: "2026-11-10T09:00:00+00:00" };
const short = { id: "m2", text: "Likes short answers", scope: "you", createdAt: "2026-11-11T09:00:00+00:00", updatedAt: "2026-11-12T09:00:00+00:00" };

type Route = { status: number; body?: unknown };
let routes: Record<string, Route>;
let sent: { key: string; body: unknown }[];

beforeEach(async () => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  sent = [];
  routes = {
    "POST /api/v1/auth/sign-in": { status: 200, body: me },
    "GET /api/v1/orgs/o1/memory/status": { status: 200, body: { enabled: true, reason: null } },
    [`GET ${BOT}`]: { status: 200, body: [short, fridays] },
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
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("Memory on the API", () => {
  it("entering an org drops the demo's memories, and the status is asked for", async () => {
    expect(state().memories).toEqual([]);
    expect(state().memoryStatus).toBeNull();
    await actions.loadMemoryStatus();
    expect(state().memoryStatus).toEqual({ enabled: true });
  });

  it("the off reason comes through as is", async () => {
    const reason = "Memory is off on this server. Set MEMORY_ENABLED=true and add OPENAI_API_KEY to turn it on.";
    routes["GET /api/v1/orgs/o1/memory/status"] = { status: 200, body: { enabled: false, reason } };
    await actions.loadMemoryStatus();
    expect(state().memoryStatus).toEqual({ enabled: false, reason });
  });

  it("loadMemories maps the API's memories onto the bot, marking corrected ones", async () => {
    await actions.loadMemories("b1");
    expect(state().memoryLists.b1).toEqual({
      status: "ready", query: "",
      items: [
        { id: "m2", botId: "b1", text: "Likes short answers", scope: "you", createdAt: "2026-11-11T09:00:00+00:00", updatedAt: "2026-11-12T09:00:00+00:00" },
        { id: "m1", botId: "b1", text: "Ships on Fridays", scope: "bot", createdAt: "2026-11-10T09:00:00+00:00" },
      ],
    });
  });

  it("a search asks the API with the query", async () => {
    routes[`GET ${BOT}?q=ships%20fridays`] = { status: 200, body: [fridays] };
    await actions.loadMemories("b1", "ships fridays");
    expect(state().memoryLists.b1.items.map((m) => m.id)).toEqual(["m1"]);
  });

  it("an older search answering late doesn't replace the newer one", async () => {
    let answerSlow: (r: Response) => void = () => {};
    const fetchMock = vi.mocked(fetch);
    const original = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => (answerSlow = resolve)));
    const slow = actions.loadMemories("b1", "old");
    await actions.loadMemories("b1");
    answerSlow(Response.json([fridays]));
    await slow;
    expect(state().memoryLists.b1.query).toBe("");
    expect(state().memoryLists.b1.items).toHaveLength(2);
    fetchMock.mockImplementation(original);
  });

  it("forgetting removes the memory; a refusal is shown as the API says it", async () => {
    await actions.loadMemories("b1");
    routes[`DELETE ${BOT}/m2`] = { status: 204 };
    await expect(actions.forgetMemory("b1", "m2")).resolves.toEqual({ ok: true });
    expect(state().memoryLists.b1.items.map((m) => m.id)).toEqual(["m1"]);

    const detail = "Only owners and admins can change what a bot learned in group chats.";
    routes[`DELETE ${BOT}/m1`] = { status: 403, body: { detail } };
    await expect(actions.forgetMemory("b1", "m1")).resolves.toEqual({ ok: false, error: detail });
    expect(state().memoryLists.b1.items.map((m) => m.id)).toEqual(["m1"]);
  });

  it("a search sent before a forget, answering after it, doesn't bring the forgotten memory back", async () => {
    await actions.loadMemories("b1");
    let answerSlow: (r: Response) => void = () => {};
    const fetchMock = vi.mocked(fetch);
    const original = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => (answerSlow = resolve)));
    const slow = actions.loadMemories("b1", "short"); // still in flight...
    routes[`DELETE ${BOT}/m2`] = { status: 204 };
    routes[`GET ${BOT}?q=short`] = { status: 200, body: [] }; // ...asked again after the forget
    await expect(actions.forgetMemory("b1", "m2")).resolves.toEqual({ ok: true });
    answerSlow(Response.json([short])); // the old answer still has m2
    await slow;
    await vi.waitFor(() => expect(state().memoryLists.b1.status).toBe("ready"));
    expect(state().memoryLists.b1).toMatchObject({ query: "short", items: [] });
    fetchMock.mockImplementation(original);
  });

  it("correcting or forgetting everything also outdates searches still in flight", async () => {
    await actions.loadMemories("b1");
    const fetchMock = vi.mocked(fetch);
    const original = fetchMock.getMockImplementation()!;
    routes[`PATCH ${BOT}/m2`] = { status: 200, body: { ...short, text: "Likes bullet points" } };
    routes[`DELETE ${BOT}`] = { status: 204 };
    routes[`GET ${BOT}?q=likes`] = { status: 200, body: [] };
    const changes = [() => actions.correctMemory("b1", "m2", "Likes bullet points"), () => actions.forgetAllMemories("b1")];
    for (const change of changes) {
      let answerSlow: (r: Response) => void = () => {};
      fetchMock.mockImplementationOnce(() => new Promise((resolve) => (answerSlow = resolve)));
      const slow = actions.loadMemories("b1", "likes");
      await change();
      answerSlow(Response.json([short]));
      await slow;
      await vi.waitFor(() => expect(state().memoryLists.b1.status).toBe("ready"));
      expect(state().memoryLists.b1.items.map((m) => m.text)).not.toContain("Likes short answers");
    }
    fetchMock.mockImplementation(original);
  });

  it("correcting sends the new text and shows what the API saved", async () => {
    await actions.loadMemories("b1");
    routes[`PATCH ${BOT}/m2`] = { status: 200, body: { ...short, text: "Likes bullet points", updatedAt: "2026-11-13T09:00:00+00:00" } };
    await expect(actions.correctMemory("b1", "m2", "Likes bullet points")).resolves.toEqual({ ok: true });
    expect(sent.find((s) => s.key === `PATCH ${BOT}/m2`)?.body).toEqual({ text: "Likes bullet points" });
    expect(state().memoryLists.b1.items[0]).toMatchObject({ text: "Likes bullet points", updatedAt: "2026-11-13T09:00:00+00:00" });
  });

  it("forget everything empties the bot's list", async () => {
    await actions.loadMemories("b1");
    routes[`DELETE ${BOT}`] = { status: 204 };
    await expect(actions.forgetAllMemories("b1")).resolves.toEqual({ ok: true });
    expect(state().memoryLists.b1.items).toEqual([]);
  });

  it("a list that can't load says why", async () => {
    routes[`GET ${BOT}`] = { status: 503, body: { detail: "Memory isn't answering right now. Try again in a moment." } };
    await actions.loadMemories("b1");
    expect(state().memoryLists.b1).toMatchObject({ status: "error", error: "Memory isn't answering right now. Try again in a moment." });
  });
});
