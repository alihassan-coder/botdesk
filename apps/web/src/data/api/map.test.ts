import { describe, expect, it } from "vitest";
import { asUtc, toApiBot, toApproval, toBot, toMessage, toOrg, toThread, toUser } from "./map";

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

  it("a chat starts read, and only DMs have a bot", () => {
    const participants = [{ type: "user" as const, id: "u1" }];
    const group = { id: "t1", kind: "group" as const, title: "Launch", botId: null, participants, lastMessageAt: "2026-11-12T08:00:00Z", lastMessagePreview: "Hi" };
    expect(toThread(group)).toEqual({ id: "t1", kind: "group", title: "Launch", participants, lastMessageAt: "2026-11-12T08:00:00Z", lastMessagePreview: "Hi", unread: 0 });
  });

  it("a message keeps the parts the web app can show, and system messages have no author id", () => {
    const message = toMessage({
      id: "m1", threadId: "t1", author: { type: "system", id: null }, status: "complete", createdAt: "2026-11-12T08:00:00Z",
      parts: [{ type: "text", text: "Hi" }, { type: "hologram", frames: 3 }],
    });
    expect(message).toEqual({
      id: "m1", threadId: "t1", author: { type: "system", id: "system" }, status: "complete", createdAt: "2026-11-12T08:00:00Z",
      parts: [{ type: "text", text: "Hi" }],
    });
  });

  it("times without a zone (SQLite) are read as UTC; ones with a zone are kept", () => {
    expect(asUtc("2026-11-12T11:36:54.520126")).toBe("2026-11-12T11:36:54.520126Z");
    expect(asUtc("2026-11-12T11:36:54Z")).toBe("2026-11-12T11:36:54Z");
    expect(asUtc("2026-11-12T11:36:54+05:00")).toBe("2026-11-12T11:36:54+05:00");
  });
});

describe("toApproval", () => {
  const api = {
    id: "a1", runId: "r1", threadId: "t1", botId: "b1", toolExecutionId: "x1", tool: "demo.send_email",
    title: "Send an email", summary: "To sara", riskClass: "external-send" as const,
    reason: "level=Ask before acting · risk=external-send · tainted=yes → ask", tainted: true,
    args: { to: "sara@acme.dev" }, finalArgs: { to: "omar@acme.dev" }, argsSchema: { type: "object", properties: {} },
    preview: [{ label: "To", value: "omar@acme.dev" }], status: "edited" as const,
    requestedAt: "2026-11-12T09:00:00", expiresAt: "2026-11-15T09:00:00", decidedAt: "2026-11-12T09:01:00", decidedBy: { id: "u1", name: "Ali" },
  };

  it("keeps what the card needs, reads times as UTC, and splits the decider into id and name", () => {
    expect(toApproval(api)).toEqual({
      id: "a1", botId: "b1", threadId: "t1", runId: "r1", riskClass: "external-send", title: "Send an email", summary: "To sara",
      reason: api.reason, tainted: true, preview: api.preview, args: api.args, finalArgs: api.finalArgs, argsSchema: api.argsSchema,
      status: "edited", requestedAt: "2026-11-12T09:00:00Z", expiresAt: "2026-11-15T09:00:00Z",
      decidedAt: "2026-11-12T09:01:00Z", decidedBy: "u1", decidedByName: "Ali",
    });
  });

  it("a waiting approval has no decision fields", () => {
    const pending = toApproval({ ...api, status: "pending", decidedAt: null, decidedBy: null, finalArgs: null });
    expect(pending).not.toHaveProperty("decidedBy");
    expect(pending).not.toHaveProperty("decidedAt");
  });
});
