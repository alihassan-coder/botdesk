import { describe, expect, it, vi } from "vitest";
import { apiMe, apiOrg, signInOnApi, withFakeApi } from "@/test/fake-api";
import { actions, getStoreSnapshot as state } from "./store";

/*
 * What API mode does where the demo only pretends: the org's default security level is saved,
 * and answering a question tells the bot. (Routines on the API: store.routines.api.test.ts.)
 */

const api = withFakeApi();

describe("the default security level for new bots, on the API", () => {
  it("comes with the organization", async () => {
    api.routes["POST /api/v1/auth/sign-in"] = { status: 200, body: { ...apiMe, organizations: [{ ...apiOrg, defaultSecurityLevel: "read-only" }] } };
    await signInOnApi();
    expect(state().org.defaultSecurityLevel).toBe("read-only");
  });

  it("setDefaultSecurityLevel saves it on the API and keeps what the API answers", async () => {
    await signInOnApi();
    api.routes["PATCH /api/v1/orgs/o1"] = { status: 200, body: { ...apiOrg, defaultSecurityLevel: "autonomous" } };
    await expect(actions.setDefaultSecurityLevel("autonomous")).resolves.toEqual({ ok: true });
    expect(api.sent.at(-1)).toEqual({ key: "PATCH /api/v1/orgs/o1", body: { defaultSecurityLevel: "autonomous" } });
    expect(state().org.defaultSecurityLevel).toBe("autonomous");
    // The org switcher's copy too, so switching away and back keeps it.
    expect(state().orgs.find((o) => o.id === "o1")?.defaultSecurityLevel).toBe("autonomous");
  });

  it("a refusal changes nothing and says why", async () => {
    await signInOnApi();
    api.routes["PATCH /api/v1/orgs/o1"] = { status: 403, body: { detail: "Only owners and admins can do that." } };
    await expect(actions.setDefaultSecurityLevel("autonomous")).resolves.toEqual({ ok: false, error: "Only owners and admins can do that." });
    expect(state().org.defaultSecurityLevel).toBe("ask-before-acting");
  });

  it("a bot hired from the marketplace starts at the org's default", async () => {
    api.routes["POST /api/v1/auth/sign-in"] = { status: 200, body: { ...apiMe, organizations: [{ ...apiOrg, defaultSecurityLevel: "read-only" }] } };
    await signInOnApi();
    await actions.createBotFromTemplate(state().templates[0].id);
    const hire = api.sent.find((r) => r.key === "POST /api/v1/orgs/o1/bots");
    expect(hire?.body).toMatchObject({ securityLevel: "read-only" });
  });
});

describe("question cards, on the API", () => {
  it("answering sends your choice to the chat as your message, so the bot gets it", async () => {
    const question = {
      id: "m1", threadId: "t1", author: { type: "bot", id: "b1" }, status: "complete", createdAt: "2026-11-12T09:00:00Z",
      parts: [{ type: "question", question: "Archive cold emails?", options: ["Yes", "No"] }],
    };
    api.routes["GET /api/v1/orgs/o1/threads/t1/runs?active=true"] = { status: 200, body: { runs: [], lastEventId: 0, replayFrom: 0 } };
    api.routes["GET /api/v1/orgs/o1/threads/t1/messages?limit=50"] = { status: 200, body: [question] };
    api.routes["POST /api/v1/orgs/o1/threads/t1/messages"] = {
      status: 201, body: { id: "m2", threadId: "t1", author: { type: "user", id: "u1" }, parts: [{ type: "text", text: "Yes" }], status: "complete", createdAt: "2026-11-12T09:01:00Z", runIds: ["r1"] },
    };
    vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
    await signInOnApi();
    actions.openThread("t1");
    await vi.waitFor(() => expect(state().threadLoads.t1?.status).toBe("ready"));

    actions.answerQuestion("m1", "Yes");

    expect(state().messages.find((m) => m.id === "m1")?.parts[0]).toMatchObject({ answered: "Yes" });
    await vi.waitFor(() => expect(api.sent.some((r) => r.key === "POST /api/v1/orgs/o1/threads/t1/messages")).toBe(true));
    expect(api.sent.find((r) => r.key === "POST /api/v1/orgs/o1/threads/t1/messages")?.body).toEqual({ text: "Yes" });
  });
});

describe("Connect apps, on the API", () => {
  const demo = {
    id: "demo", name: "Demo", version: "0.1.0", description: "Tools to try approvals with.",
    tools: [{ name: "demo.send_email", title: "Send email", description: "Sends an email.", risk: "external-send" }],
  };

  it("loadPlugins lists the plugins the server loaded, with their tools", async () => {
    api.routes["GET /api/v1/orgs/o1/plugins"] = { status: 200, body: [demo] };
    await signInOnApi();
    await actions.loadPlugins();
    expect(state().plugins).toEqual({ status: "ready", items: [demo] });
  });

  it("says so when they can't be loaded", async () => {
    api.routes["GET /api/v1/orgs/o1/plugins"] = { status: 500, body: { detail: "Oops" } };
    await signInOnApi();
    await actions.loadPlugins();
    expect(state().plugins.status).toBe("error");
  });
});
