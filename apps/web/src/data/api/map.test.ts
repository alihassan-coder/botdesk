import { describe, expect, it } from "vitest";
import { toApiBot, toBot, toOrg, toUser } from "./map";

describe("API → web shapes", () => {
  it("a user gets the role they hold in the org and shows as online", () => {
    expect(toUser({ id: "u1", name: "Zara", email: "zara@example.com", handle: "zara" }, "admin")).toEqual({
      id: "u1", name: "Zara", email: "zara@example.com", handle: "zara", role: "admin", presence: "online",
    });
  });

  it("an org drops the viewer's role, which belongs to the user", () => {
    expect(toOrg({ id: "o1", name: "Acme", slug: "acme", plan: "free", role: "owner" })).toEqual({ id: "o1", name: "Acme", slug: "acme", plan: "free" });
  });

  const apiBot = {
    id: "b1", name: "Scout", handle: "scout", role: "Research", description: "Finds things.", instructions: "Be brief.",
    avatarColor: "sky", modelId: "openai:gpt-5.5", securityLevel: "read-only", monthlyBudgetUsd: 30, status: "idle",
    createdAt: "2026-11-12T08:00:00Z",
  } as const;

  it("a bot gets safe defaults for what the API doesn't have yet, and the web's model id", () => {
    expect(toBot(apiBot)).toEqual({
      id: "b1", name: "Scout", handle: "scout", role: "Research", description: "Finds things.", instructions: "Be brief.",
      avatarColor: "sky", modelId: "m_gpt", securityLevel: "read-only", monthlyBudgetUsd: 30, status: "idle",
      createdAt: "2026-11-12T08:00:00Z", computerMode: "none", connectionIds: [], spentThisMonthUsd: 0,
    });
  });

  it("an empty or unknown model id passes through, so the screen can say 'Default model'", () => {
    expect(toBot({ ...apiBot, modelId: "" }).modelId).toBe("");
    expect(toBot({ ...apiBot, modelId: "acme:custom-1" }).modelId).toBe("acme:custom-1");
  });

  it("sending a bot keeps only the fields the API takes, with whole-dollar budgets", () => {
    expect(toApiBot({ name: "Scout", modelId: "m_claude", monthlyBudgetUsd: 12.6, computerMode: "own" })).toEqual({
      name: "Scout", modelId: "anthropic:claude-sonnet-5.5", monthlyBudgetUsd: 13,
    });
  });
});
