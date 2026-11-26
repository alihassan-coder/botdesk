import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiMe, apiOrg, signInOnApi, withFakeApi } from "@/test/fake-api";
import { createMessageCache, messageCache, type CachedChat } from "./message-cache";
import { actions, getStoreSnapshot as state } from "./store";

/*
 * jsdom has no IndexedDB, so the store's cache is the real one over a Map here. (The store is loaded
 * by the test setup before any vi.mock here could apply, so its cache's methods are swapped instead.)
 */
const kept = new Map<string, CachedChat>();
const overMap = createMessageCache(async () => ({
  get: async (key) => kept.get(key),
  put: async (chat) => void kept.set(chat.key, chat),
  keysByAge: async () => [...kept.values()].sort((a, b) => a.savedAt - b.savedAt).map((c) => c.key),
  remove: async (keys) => keys.forEach((key) => kept.delete(key)),
  clear: async () => kept.clear(),
}));

/** The browser's EventSource, doing nothing: these tests don't need a chat's live updates. */
class QuietEventSource {
  addEventListener() {}
  close() {}
}

const message = (id: string, text: string, createdAt = "2026-11-26T09:00:00Z") => ({
  id, threadId: "t1", author: { type: "bot", id: "b1" }, parts: [{ type: "text", text }], status: "complete", createdAt,
});
const texts = () => state().messages.filter((m) => m.threadId === "t1").map((m) => (m.parts[0]?.type === "text" ? m.parts[0].text : ""));
const PAGE = "GET /api/v1/orgs/o1/threads/t1/messages?limit=50";

describe("messages kept on this device", () => {
  const api = withFakeApi();

  beforeEach(() => {
    kept.clear();
    vi.stubGlobal("EventSource", QuietEventSource);
    vi.spyOn(messageCache, "read").mockImplementation(overMap.read);
    vi.spyOn(messageCache, "save").mockImplementation(overMap.save);
    vi.spyOn(messageCache, "clear").mockImplementation(overMap.clear);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    kept.clear();
  });

  it("a chat opens with what was kept here, then the API's page replaces it, and is kept again", async () => {
    kept.set("u1/o1/t1", { key: "u1/o1/t1", savedAt: 1, messages: [message("m1", "From last time")] as CachedChat["messages"] });
    let answer = () => {};
    api.routes[PAGE] = { status: 200, wait: new Promise<void>((resolve) => (answer = resolve)), body: [message("m1", "Hi"), message("m2", "Since then")] };
    await signInOnApi();

    const close = actions.openThread("t1");
    await vi.waitFor(() => expect(texts()).toEqual(["From last time"]));
    expect(state().threadLoads.t1?.status).toBe("loading");

    answer();
    await vi.waitFor(() => expect(state().threadLoads.t1?.status).toBe("ready"));
    expect(texts()).toEqual(["Hi", "Since then"]);
    await vi.waitFor(() => expect(kept.get("u1/o1/t1")?.messages.map((m) => m.id)).toEqual(["m1", "m2"]));
    close();
  });

  it("what was kept but the API no longer has goes, even when the page is empty", async () => {
    kept.set("u1/o1/t1", { key: "u1/o1/t1", savedAt: 1, messages: [message("m1", "Removed on the server since")] as CachedChat["messages"] });
    let answer = () => {};
    api.routes[PAGE] = { status: 200, wait: new Promise<void>((resolve) => (answer = resolve)), body: [] };
    await signInOnApi();

    actions.openThread("t1");
    await vi.waitFor(() => expect(texts()).toEqual(["Removed on the server since"]));
    answer();
    await vi.waitFor(() => expect(state().threadLoads.t1?.status).toBe("ready"));
    expect(texts()).toEqual([]);
    await vi.waitFor(() => expect(kept.has("u1/o1/t1")).toBe(false));
  });

  it("a page that fails leaves what was kept on screen", async () => {
    kept.set("u1/o1/t1", { key: "u1/o1/t1", savedAt: 1, messages: [message("m1", "From last time")] as CachedChat["messages"] });
    api.routes[PAGE] = { status: 500, body: { detail: "Down for a moment." } };
    await signInOnApi();

    actions.openThread("t1");
    await vi.waitFor(() => expect(state().threadLoads.t1?.status).toBe("error"));
    expect(texts()).toEqual(["From last time"]);
  });

  it("signing out forgets everything kept here", async () => {
    api.routes[PAGE] = { status: 200, body: [message("m1", "Hi")] };
    await signInOnApi();
    actions.openThread("t1");
    await vi.waitFor(() => expect(kept.size).toBe(1));

    await actions.signOut();
    await vi.waitFor(() => expect(kept.size).toBe(0));
  });

  it("an expired session forgets everything kept here too", async () => {
    api.routes[PAGE] = { status: 200, body: [message("m1", "Hi")] };
    await signInOnApi();
    actions.openThread("t1");
    await vi.waitFor(() => expect(kept.size).toBe(1));

    api.routes["GET /api/v1/auth/me"] = { status: 401, body: { detail: "Sign in again." } };
    await actions.restoreSession();
    expect(state().authStatus).toBe("signed-out");
    await vi.waitFor(() => expect(kept.size).toBe(0));
  });

  it("a password reset (which signs out every device) forgets everything kept here", async () => {
    api.routes[PAGE] = { status: 200, body: [message("m1", "Hi")] };
    await signInOnApi();
    actions.openThread("t1");
    await vi.waitFor(() => expect(kept.size).toBe(1));

    api.routes["POST /api/v1/auth/reset-password"] = { status: 200, body: { message: "Password changed." } };
    await expect(actions.resetPassword("token", "a-new-long-password")).resolves.toEqual({ ok: true });
    await vi.waitFor(() => expect(kept.size).toBe(0));
  });

  it("a chat closing while you sign out isn't saved back", async () => {
    api.routes[PAGE] = { status: 200, body: [message("m1", "Hi")] };
    await signInOnApi();
    const close = actions.openThread("t1");
    await vi.waitFor(() => expect(kept.size).toBe(1));

    let answer = () => {};
    api.routes["POST /api/v1/auth/sign-out"] = { status: 204, wait: new Promise<void>((resolve) => (answer = resolve)) };
    const out = actions.signOut();
    close(); // a chat saves itself as it closes
    answer();
    await out;
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(kept.size).toBe(0);
  });

  it("switching organization forgets the other one's chats", async () => {
    const other = { ...apiOrg, id: "o2", name: "Side project", slug: "side" };
    api.routes["POST /api/v1/auth/sign-in"] = { status: 200, body: { ...apiMe, organizations: [apiOrg, other] } };
    api.routes[PAGE] = { status: 200, body: [message("m1", "Hi")] };
    await signInOnApi();
    actions.openThread("t1");
    await vi.waitFor(() => expect(kept.size).toBe(1));

    await actions.switchOrg("o2");
    await vi.waitFor(() => expect(kept.size).toBe(0));
  });
});

describe("messages kept on this device, in the demo", () => {
  it("are never read, saved or cleared", async () => {
    const used = [vi.spyOn(messageCache, "read"), vi.spyOn(messageCache, "save"), vi.spyOn(messageCache, "clear")];
    await actions.signIn("ali@acme.dev", "botdesk123");
    actions.openThread("t_chief")();
    await actions.signOut();
    used.forEach((spy) => expect(spy).not.toHaveBeenCalled());
    vi.restoreAllMocks();
  });
});
