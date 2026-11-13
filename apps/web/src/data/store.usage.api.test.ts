import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot as state } from "./store";

/*
 * Usage & budgets when NEXT_PUBLIC_API_URL is set. fetch is faked per route ("METHOD path"),
 * so these never touch a network.
 */

const org = { id: "o1", name: "Zara's team", slug: "zara-team", plan: "free", role: "owner" };
const me = { user: { id: "u1", name: "Zara", email: "zara@example.com", handle: "zara" }, organizations: [org] };
const scout = {
  id: "b1", name: "Scout", handle: "scout", role: "Research", description: "", instructions: "", avatarColor: "sky",
  modelId: "", securityLevel: "ask-before-acting", monthlyBudgetUsd: 40, status: "idle", createdAt: "2026-11-12T08:00:00Z",
};
const day = (date: string, modelsUsd: number) => ({ date, modelsUsd, computersUsd: 0, inputTokens: 1000, outputTokens: 200, unpricedTokens: 0 });
const report = {
  days: [day("2026-11-12", 1.5), day("2026-11-13", 0.25)],
  monthStart: "2026-11-01",
  monthToDateUsd: 33.5,
  orgBudgetUsd: 200,
  unpricedTokens: 4200,
  bots: [{ botId: "b1", name: "Scout", spentUsd: 33.5, budgetUsd: 40, inputTokens: 1, outputTokens: 1, unpricedTokens: 0 }],
  pricesChecked: "2026-11-13",
};

type Route = { status: number; body?: unknown };
let routes: Record<string, Route>;
let sent: { key: string; body: unknown }[];

beforeEach(async () => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  sent = [];
  routes = {
    "POST /api/v1/auth/sign-in": { status: 200, body: me },
    "GET /api/v1/orgs/o1/bots": { status: 200, body: [scout] },
    "GET /api/v1/orgs/o1/threads": { status: 200, body: [] },
    "POST /api/v1/orgs/o1/threads/dm": { status: 404, body: { detail: "Not found" } },
    "GET /api/v1/orgs/o1/usage?days=14": { status: 200, body: report },
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
  await vi.waitFor(() => expect(state().usageLoading).toBe(false));
  await vi.waitFor(() => expect(state().botsLoading).toBe(false));
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("Usage & budgets on the API", () => {
  it("entering the org loads its usage instead of the demo's", () => {
    expect(state().usage).toEqual({
      days: [
        { date: "2026-11-12", tokensUsd: 1.5, computerUsd: 0, inputTokens: 1000, outputTokens: 200, unpricedTokens: 0 },
        { date: "2026-11-13", tokensUsd: 0.25, computerUsd: 0, inputTokens: 1000, outputTokens: 200, unpricedTokens: 0 },
      ],
      monthToDateUsd: 33.5,
      unpricedTokens: 4200,
      orgBudgetUsd: 200,
    });
  });

  it("each bot shows what it spent this month, whichever arrived first", () => {
    expect(state().bots.find((b) => b.id === "b1")).toMatchObject({ spentThisMonthUsd: 33.5, monthlyBudgetUsd: 40 });
  });

  it("loadUsage fetches the latest report", async () => {
    routes["GET /api/v1/orgs/o1/usage?days=14"] = { status: 200, body: { ...report, monthToDateUsd: 39, bots: [{ ...report.bots[0], spentUsd: 39 }] } };
    await actions.loadUsage();
    expect(state().usage.monthToDateUsd).toBe(39);
    expect(state().bots[0].spentThisMonthUsd).toBe(39);
  });

  it("a report that fails to load keeps what was there", async () => {
    routes["GET /api/v1/orgs/o1/usage?days=14"] = { status: 500, body: { detail: "Oops" } };
    await actions.loadUsage();
    expect(state().usage.monthToDateUsd).toBe(33.5);
    expect(state().usageLoading).toBe(false);
  });

  it("setOrgBudget saves on the API; null or 0 removes the limit", async () => {
    routes["PATCH /api/v1/orgs/o1"] = { status: 200, body: { ...org, monthlyBudgetUsd: 300 } };
    await expect(actions.setOrgBudget(300)).resolves.toEqual({ ok: true });
    expect(sent.at(-1)).toEqual({ key: "PATCH /api/v1/orgs/o1", body: { monthlyBudgetUsd: 300 } });
    expect(state().usage.orgBudgetUsd).toBe(300);

    await actions.setOrgBudget(0);
    expect(sent.at(-1)?.body).toEqual({ monthlyBudgetUsd: null });
    expect(state().usage.orgBudgetUsd).toBeUndefined();
  });

  it("setOrgBudget passes on a refusal and keeps the budget", async () => {
    routes["PATCH /api/v1/orgs/o1"] = { status: 403, body: { detail: "Only owners and admins can do that." } };
    await expect(actions.setOrgBudget(5)).resolves.toEqual({ ok: false, error: "Only owners and admins can do that." });
    expect(state().usage.orgBudgetUsd).toBe(200);
  });
});
