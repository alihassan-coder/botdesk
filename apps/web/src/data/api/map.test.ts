import { describe, expect, it } from "vitest";
import { asUtc, toApiBot, toApproval, toBot, toCloudComputer, toComputerProvider, toMemoryKey, toMessage, toOrg, toThread, toUsage, toUser } from "./map";

describe("API → web shapes", () => {
  it("a user gets the role they hold in the org and shows as online", () => {
    expect(toUser({ id: "u1", name: "Zara", email: "zara@example.com", handle: "zara" }, "admin")).toEqual({
      id: "u1", name: "Zara", email: "zara@example.com", handle: "zara", role: "admin", presence: "online",
    });
  });

  it("an org drops the viewer's role, which belongs to the user, and keeps its default for new bots and its ceiling", () => {
    const apiOrg = { id: "o1", name: "Acme", slug: "acme", role: "owner", defaultSecurityLevel: "read-only", maxSecurityLevel: "ask-before-acting" } as const;
    expect(toOrg(apiOrg)).toEqual({
      id: "o1", name: "Acme", slug: "acme", defaultSecurityLevel: "read-only", maxSecurityLevel: "ask-before-acting",
      // Sent without the chat history settings: summaries on, messages kept forever.
      historySummaries: true, historyRetentionDays: null,
    });
    expect(toOrg({ ...apiOrg, historySummaries: false, historyRetentionDays: 90 })).toMatchObject({ historySummaries: false, historyRetentionDays: 90 });
  });

  it("a memory key keeps only its provider, last 4 and check time; none means the server's", () => {
    expect(toMemoryKey({ provider: "gemini", keyHint: "abcd", checkedAt: "2026-11-26T08:00:00" })).toEqual({
      provider: "gemini", keyHint: "abcd", checkedAt: "2026-11-26T08:00:00Z",
    });
    expect(toMemoryKey({ provider: null, keyHint: null, checkedAt: null })).toEqual({});
  });

  const apiBot = {
    id: "b1", name: "Scout", handle: "scout", role: "Research", description: "Finds things.", instructions: "Be brief.",
    avatarColor: "sky", modelId: "openai:gpt-5.5", securityLevel: "read-only", monthlyBudgetUsd: 30, memoryEnabled: false, status: "idle",
    createdAt: "2026-11-12T08:00:00Z",
  } as const;

  it("a bot gets safe defaults for what the API doesn't have yet, and keeps its model id", () => {
    expect(toBot(apiBot)).toEqual({
      id: "b1", name: "Scout", handle: "scout", role: "Research", description: "Finds things.", instructions: "Be brief.",
      avatarColor: "sky", modelId: "openai:gpt-5.5", securityLevel: "read-only", monthlyBudgetUsd: 30, memoryEnabled: false, status: "idle",
      createdAt: "2026-11-12T08:00:00Z", computer: "browser", computerMode: "none", connectionIds: [], spentThisMonthUsd: 0,
    });
    // ADR 0020: a newer API says which computer the bot works on.
    expect(toBot({ ...apiBot, computer: "cloud" }).computer).toBe("cloud");
  });

  it("an empty or unknown model id passes through, so the screen can say 'Default model'", () => {
    expect(toBot({ ...apiBot, modelId: "" }).modelId).toBe("");
    expect(toBot({ ...apiBot, modelId: "custom-1:llama3.2:latest" }).modelId).toBe("custom-1:llama3.2:latest");
  });

  it("sending a bot keeps only the fields the API takes, with whole-dollar budgets", () => {
    expect(toApiBot({ name: "Scout", modelId: "anthropic:claude-opus-5-5", monthlyBudgetUsd: 12.6, memoryEnabled: false, computerMode: "own" })).toEqual({
      name: "Scout", modelId: "anthropic:claude-opus-5-5", monthlyBudgetUsd: 13, memoryEnabled: false,
    });
    expect(toApiBot({ computer: "cloud" })).toEqual({ computer: "cloud" });
  });

  it("a chat starts read, and only DMs have a bot", () => {
    const participants = [{ type: "user" as const, id: "u1" }];
    const group = { id: "t1", kind: "group" as const, title: "Launch", botId: null, leadBotId: null, createdBy: null, participants, lastMessageAt: "2026-11-12T08:00:00Z", lastMessagePreview: "Hi" };
    expect(toThread(group)).toEqual({ id: "t1", kind: "group", title: "Launch", participants, lastMessageAt: "2026-11-12T08:00:00Z", lastMessagePreview: "Hi", unread: 0 });
  });

  it("a group keeps its lead and who made it", () => {
    const group = {
      id: "t1", kind: "group" as const, title: "Launch", botId: null, leadBotId: "b1", createdBy: "u1",
      participants: [], lastMessageAt: "2026-11-12T08:00:00Z", lastMessagePreview: "",
    };
    expect(toThread(group)).toMatchObject({ leadBotId: "b1", createdBy: "u1" });
  });

  it("a chat's unread count comes from the API, and reads as 0 when it isn't sent", () => {
    const dm = {
      id: "t1", kind: "dm" as const, title: "Scout", botId: "b1", leadBotId: null, createdBy: "u1",
      participants: [], lastMessageAt: "2026-11-12T08:00:00Z", lastMessagePreview: "Found 3.",
    };
    expect(toThread({ ...dm, unread: 3 }).unread).toBe(3);
    expect(toThread(dm).unread).toBe(0);
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

  it("a saved reply keeps its tool lines, so a reloaded chat still says what the bot used", () => {
    const line = { type: "tool-call", toolExecutionId: "x1", tool: "demo.send_email", status: "succeeded" };
    const message = toMessage({
      id: "m1", threadId: "t1", author: { type: "bot", id: "b1" }, status: "complete", createdAt: "2026-11-12T08:00:00Z",
      parts: [{ type: "approval", approvalId: "a1" }, line, { type: "text", text: "Sent." }],
    });
    expect(message.parts).toEqual([{ type: "approval", approvalId: "a1" }, line, { type: "text", text: "Sent." }]);
  });

  it("an attached file in the shared folder has no botId (the API's null)", () => {
    const file = { type: "file", fileId: "f1", botId: null, path: "chat/brief.pdf", contentType: "application/pdf", sizeBytes: 2048 };
    const message = toMessage({
      id: "m1", threadId: "t1", author: { type: "user", id: "u1" }, status: "complete", createdAt: "2026-11-12T08:00:00Z",
      parts: [file, { ...file, fileId: "f2", botId: "b1" }],
    });
    expect(message.parts).toEqual([
      { type: "file", fileId: "f1", path: "chat/brief.pdf", contentType: "application/pdf", sizeBytes: 2048 },
      { type: "file", fileId: "f2", botId: "b1", path: "chat/brief.pdf", contentType: "application/pdf", sizeBytes: 2048 },
    ]);
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
      id: "a1", botId: "b1", threadId: "t1", runId: "r1", tool: "demo.send_email", riskClass: "external-send", title: "Send an email", summary: "To sara",
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

describe("toUsage", () => {
  const report = {
    days: [{ date: "2026-11-13", modelsUsd: 1.5, computersUsd: 0, inputTokens: 10, outputTokens: 2, unpricedTokens: 0 }],
    monthStart: "2026-11-01", monthToDateUsd: 1.5, orgBudgetUsd: null, unpricedTokens: 7, pricesChecked: "2026-11-13",
    bots: [{ botId: "b1", name: "Scout", spentUsd: 1.5, budgetUsd: null, inputTokens: 10, outputTokens: 2, unpricedTokens: 0 }],
  };

  it("keeps daily model spend as the chart's tokens series, and each bot's spend by id", () => {
    expect(toUsage(report)).toEqual({
      summary: {
        days: [{ date: "2026-11-13", tokensUsd: 1.5, computerUsd: 0, inputTokens: 10, outputTokens: 2, unpricedTokens: 0 }],
        monthToDateUsd: 1.5, unpricedTokens: 7,
      },
      spentByBot: { b1: 1.5 },
    });
  });

  it("an org budget of null is no limit; a number is kept", () => {
    expect(toUsage(report).summary.orgBudgetUsd).toBeUndefined();
    expect(toUsage({ ...report, orgBudgetUsd: 200 }).summary.orgBudgetUsd).toBe(200);
  });
});

describe("cloud computers (ADR 0020)", () => {
  it("a provider keeps its key's last 4, when it was checked and whether Orgo refused it; none is empty", () => {
    expect(toComputerProvider({ provider: "orgo", keyHint: "abcd", checkedAt: "2026-11-27T08:00:00", status: "key_refused" })).toEqual({
      provider: "orgo", keyHint: "abcd", checkedAt: "2026-11-27T08:00:00Z", status: "key_refused",
    });
    expect(toComputerProvider({ provider: null, keyHint: null, checkedAt: null, status: null })).toEqual({});
  });

  it("a computer drops what isn't known, and reads times as UTC", () => {
    expect(toCloudComputer({
      status: "running", name: "botdesk-scout", remoteId: "c1", cpu: 2, ram: 8, region: null, startedAt: "2026-11-27T09:00:00",
      lastUsedAt: null, idleStopsAt: "2026-11-27T09:20:00Z", error: null, orgoUrl: null, apps: [], previews: [],
    })).toEqual({
      status: "running", name: "botdesk-scout", cpu: 2, ram: 8, startedAt: "2026-11-27T09:00:00Z", idleStopsAt: "2026-11-27T09:20:00Z", apps: [], previews: [],
    });
  });
});
