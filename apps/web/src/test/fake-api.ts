import { afterEach, beforeEach, expect, vi } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";

/*
 * API mode for a test file: NEXT_PUBLIC_API_URL is set and fetch is faked per route
 * ("METHOD path"), so nothing touches a network. Call `withFakeApi()` at the top of a file or describe,
 * then `signInOnApi()` in a test (or a beforeEach) to enter Zara's org "o1" with bot "b1".
 */

type Route = { status: number; body?: unknown };

export const apiOrg = { id: "o1", name: "Zara's team", slug: "zara-team", role: "owner", defaultSecurityLevel: "ask-before-acting" };
export const apiMe = { user: { id: "u1", name: "Zara", email: "zara@example.com", handle: "zara" }, organizations: [apiOrg] };
export const apiScout = {
  id: "b1", name: "Scout", handle: "scout", role: "Research", description: "", instructions: "", avatarColor: "sky",
  modelId: "", securityLevel: "ask-before-acting", monthlyBudgetUsd: 40, memoryEnabled: true, status: "idle",
  createdAt: "2026-11-12T08:00:00Z",
};
export const apiDm = {
  id: "t1", kind: "dm", title: "Scout", botId: "b1", participants: [{ type: "user", id: "u1" }, { type: "bot", id: "b1" }],
  lastMessageAt: "2026-11-12T08:00:00Z", lastMessagePreview: "",
};

export interface FakeApi {
  routes: Record<string, Route>;
  /** Every request made, in order, with its JSON body. */
  sent: { key: string; body: unknown }[];
}

export function withFakeApi(): FakeApi {
  const api: FakeApi = { routes: {}, sent: [] };
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
    api.sent.length = 0;
    api.routes = {
      "POST /api/v1/auth/sign-in": { status: 200, body: apiMe },
      "GET /api/v1/orgs/o1/members": { status: 200, body: [{ ...apiMe.user, role: "owner" }] },
      "GET /api/v1/orgs/o1/bots": { status: 200, body: [apiScout] },
      "GET /api/v1/orgs/o1/threads": { status: 200, body: [apiDm] },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const key = `${init?.method ?? "GET"} ${url.replace("http://api.test", "")}`;
        api.sent.push({ key, body: init?.body ? JSON.parse(String(init.body)) : undefined });
        const route = api.routes[key] ?? { status: 404, body: { detail: "Not found" } };
        return route.body === undefined ? new Response(null, { status: route.status }) : Response.json(route.body, { status: route.status });
      }),
    );
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });
  return api;
}

/** Signs Zara in on the fake API and waits for her org's bots and chats. */
export async function signInOnApi() {
  await actions.signIn("zara@example.com", "long-enough");
  await vi.waitFor(() => expect(getStoreSnapshot().botsLoading).toBe(false));
}
