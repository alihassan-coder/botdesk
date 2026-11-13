import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot as state, isDemoMode } from "./store";

/*
 * The store when NEXT_PUBLIC_API_URL is set: auth and the organization come from the API.
 * fetch is faked per route, so these tests never touch a network.
 */

const org = { id: "o1", name: "Zara's team", slug: "zara-team", plan: "free", role: "owner" };
const me = { user: { id: "u1", name: "Zara", email: "zara@example.com", handle: "zara" }, organizations: [org] };
const members = [
  { ...me.user, role: "owner" },
  { id: "u2", name: "Omar", email: "omar@example.com", handle: "omar", role: "member" },
];

type Route = { status: number; body?: unknown };
let routes: Record<string, Route>;
const calls: string[] = [];

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  calls.length = 0;
  routes = {
    "GET /api/v1/auth/me": { status: 200, body: me },
    "POST /api/v1/auth/sign-in": { status: 200, body: me },
    "POST /api/v1/auth/sign-out": { status: 204 },
    "GET /api/v1/orgs/o1/members": { status: 200, body: members },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url.replace("http://api.test", "")}`;
      calls.push(key);
      const route = routes[key] ?? { status: 404, body: { detail: "Not found" } };
      return route.body === undefined ? new Response(null, { status: route.status }) : Response.json(route.body, { status: route.status });
    }),
  );
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

const currentUser = () => state().users.find((u) => u.id === state().currentUserId);

describe("auth on the API", () => {
  it("signIn signs you in as the API's user, in your first organization, and loads its members", async () => {
    await expect(actions.signIn("zara@example.com", "long-enough")).resolves.toEqual({ ok: true });
    expect(state().authStatus).toBe("signed-in");
    expect(currentUser()).toMatchObject({ name: "Zara", role: "owner" });
    expect(state().org).toEqual({ id: "o1", name: "Zara's team", slug: "zara-team", plan: "free" });
    await vi.waitFor(() => expect(state().users.map((u) => u.name)).toEqual(["Zara", "Omar"]));
    // The cookie is the session; nothing about it is kept in localStorage.
    expect(localStorage.getItem("botdesk.session")).toBeNull();
  });

  it("signIn shows the API's message when the password is wrong", async () => {
    routes["POST /api/v1/auth/sign-in"] = { status: 401, body: { detail: "That email and password don't match." } };
    await expect(actions.signIn("zara@example.com", "nope")).resolves.toEqual({ ok: false, error: "That email and password don't match." });
    expect(state().authStatus).not.toBe("signed-in");
  });

  it("restoreSession asks the API who you are", async () => {
    await actions.restoreSession();
    expect(state().authStatus).toBe("signed-in");

    routes["GET /api/v1/auth/me"] = { status: 401, body: { detail: "Sign in to continue." } };
    actions.reset();
    await actions.restoreSession();
    expect(state().authStatus).toBe("signed-out");
  });

  it("signOut ends the session on the API too", async () => {
    await actions.signIn("zara@example.com", "long-enough");
    await actions.signOut();
    expect(calls).toContain("POST /api/v1/auth/sign-out");
    expect(state().authStatus).toBe("signed-out");
  });
});

describe("organization on the API", () => {
  beforeEach(async () => {
    await actions.signIn("zara@example.com", "long-enough");
  });

  it("updateOrg saves on the API and shows what it saved", async () => {
    routes["PATCH /api/v1/orgs/o1"] = { status: 200, body: { ...org, name: "Zara Inc", slug: "zara-inc" } };
    await expect(actions.updateOrg({ name: "Zara Inc", slug: "zara-inc" })).resolves.toEqual({ ok: true });
    expect(state().org).toMatchObject({ name: "Zara Inc", slug: "zara-inc" });
  });

  it("updateOrg keeps the old name and explains when the address is taken", async () => {
    routes["PATCH /api/v1/orgs/o1"] = { status: 409, body: { detail: "That address is taken. Try another." } };
    await expect(actions.updateOrg({ slug: "taken" })).resolves.toEqual({ ok: false, error: "That address is taken. Try another." });
    expect(state().org.slug).toBe("zara-team");
  });
});

describe("members and invitations on the API", () => {
  const invite = { id: "i1", email: "new@example.com", role: "member", createdAt: "2026-11-12T08:00:00Z", expiresAt: "2026-11-19T08:00:00Z" };

  beforeEach(async () => {
    routes["GET /api/v1/orgs/o1/invitations"] = { status: 200, body: [] };
    await actions.signIn("zara@example.com", "long-enough");
    await vi.waitFor(() => expect(state().users).toHaveLength(2));
  });

  it("inviteMember returns the link to share and lists the invite as pending, without keeping the link", async () => {
    routes["POST /api/v1/orgs/o1/invitations"] = { status: 201, body: { ...invite, inviteUrl: "http://localhost:3000/invite/secret" } };
    await expect(actions.inviteMember("new@example.com", "member")).resolves.toEqual({ ok: true, inviteUrl: "http://localhost:3000/invite/secret" });
    expect(state().invitations).toEqual([invite]);
  });

  it("revokeInvitation removes the pending invite", async () => {
    routes["POST /api/v1/orgs/o1/invitations"] = { status: 201, body: { ...invite, inviteUrl: "x" } };
    routes["DELETE /api/v1/orgs/o1/invitations/i1"] = { status: 204 };
    await actions.inviteMember("new@example.com", "member");
    await expect(actions.revokeInvitation("i1")).resolves.toEqual({ ok: true });
    expect(state().invitations).toEqual([]);
  });

  it("changeMemberRole saves the role the API answers with, and explains a refusal", async () => {
    routes["PATCH /api/v1/orgs/o1/members/u2"] = { status: 200, body: { ...members[1], role: "admin" } };
    await expect(actions.changeMemberRole("u2", "admin")).resolves.toEqual({ ok: true });
    expect(state().users.find((u) => u.id === "u2")?.role).toBe("admin");

    routes["PATCH /api/v1/orgs/o1/members/u1"] = { status: 409, body: { detail: "An organization needs at least one owner." } };
    await expect(actions.changeMemberRole("u1", "member")).resolves.toEqual({ ok: false, error: "An organization needs at least one owner." });
    expect(currentUser()?.role).toBe("owner");
  });

  it("removeMember takes them off the list", async () => {
    routes["DELETE /api/v1/orgs/o1/members/u2"] = { status: 204 };
    await expect(actions.removeMember("u2")).resolves.toEqual({ ok: true });
    expect(state().users.map((u) => u.id)).toEqual(["u1"]);
  });

  it("acceptInvitation switches you to the org you joined, with your role there", async () => {
    const other = { id: "o2", name: "Globex", slug: "globex", plan: "team", role: "member" };
    routes["POST /api/v1/invitations/accept"] = { status: 200, body: other };
    routes["GET /api/v1/orgs/o2/members"] = { status: 200, body: [{ ...me.user, role: "member" }] };
    await expect(actions.acceptInvitation("secret")).resolves.toEqual({ ok: true });
    expect(state().org).toMatchObject({ id: "o2", name: "Globex" });
    expect(currentUser()?.role).toBe("member");
  });
});

describe("switching organizations on the API", () => {
  const globex = { id: "o2", name: "Globex", slug: "globex", plan: "team", role: "member" };

  beforeEach(() => {
    routes["GET /api/v1/auth/me"] = { status: 200, body: { ...me, organizations: [org, globex] } };
    routes["POST /api/v1/auth/sign-in"] = routes["GET /api/v1/auth/me"];
    routes["GET /api/v1/orgs/o2/members"] = { status: 200, body: [{ ...me.user, role: "member" }] };
  });

  it("lists every organization you belong to, starting in the first one", async () => {
    await actions.signIn("zara@example.com", "long-enough");
    expect(state().orgs.map((o) => [o.name, o.role])).toEqual([["Zara's team", "owner"], ["Globex", "member"]]);
    expect(state().org.id).toBe("o1");
  });

  it("switchOrg makes it current, with your role there, loads its people, and is remembered", async () => {
    await actions.signIn("zara@example.com", "long-enough");
    await actions.switchOrg("o2");
    expect(state().org).toMatchObject({ id: "o2", name: "Globex" });
    expect(currentUser()?.role).toBe("member");
    expect(calls).toContain("GET /api/v1/orgs/o2/members");
    expect(localStorage.getItem("botdesk.org")).toBe("o2");

    // Next visit starts where you left off.
    actions.reset();
    await actions.restoreSession();
    expect(state().org.id).toBe("o2");
  });

  it("falls back to the first organization when the remembered one is gone", async () => {
    localStorage.setItem("botdesk.org", "o-you-left");
    await actions.restoreSession();
    expect(state().org.id).toBe("o1");
  });

  it("acceptInvitation adds the org to your list and remembers it", async () => {
    await actions.signIn("zara@example.com", "long-enough");
    const initech = { id: "o3", name: "Initech", slug: "initech", plan: "free", role: "admin" };
    routes["POST /api/v1/invitations/accept"] = { status: 200, body: initech };
    await actions.acceptInvitation("secret");
    expect(state().orgs.map((o) => o.id)).toEqual(["o1", "o2", "o3"]);
    expect(localStorage.getItem("botdesk.org")).toBe("o3");
  });
});

describe("bots on the API", () => {
  const scout = {
    id: "b1", name: "Scout", handle: "scout", role: "Research", description: "", instructions: "", avatarColor: "sky",
    modelId: "", securityLevel: "ask-before-acting", monthlyBudgetUsd: 50, status: "idle", createdAt: "2026-11-12T08:00:00Z",
  };
  const newBot = {
    name: "Writer", role: "Docs", description: "", avatarColor: "rose", instructions: "", modelId: "m_claude",
    securityLevel: "read-only", computerMode: "own", monthlyBudgetUsd: 20,
  } as const;

  const dm = (id: string, botId: string, title: string) => ({
    id, kind: "dm", title, botId, participants: [{ type: "user", id: "u1" }, { type: "bot", id: botId }],
    lastMessageAt: "2026-11-12T08:00:00Z", lastMessagePreview: "",
  });

  beforeEach(async () => {
    routes["GET /api/v1/orgs/o1/bots"] = { status: 200, body: [scout] };
    routes["GET /api/v1/orgs/o1/threads"] = { status: 200, body: [dm("t1", "b1", "Scout")] };
    await actions.signIn("zara@example.com", "long-enough");
    await vi.waitFor(() => expect(state().bots.map((b) => b.name)).toEqual(["Scout"]));
  });

  it("the org's bots and your chats replace the demo's", () => {
    expect(state().threads).toEqual([expect.objectContaining({ id: "t1", kind: "dm", botId: "b1", title: "Scout" })]);
    expect(state().messages).toEqual([]);
    expect(state().approvals).toEqual([]);
  });

  it("createBot hires on the API and returns the new bot's chat", async () => {
    routes["POST /api/v1/orgs/o1/bots"] = { status: 201, body: { ...scout, id: "b2", name: "Writer", handle: "writer" } };
    routes["POST /api/v1/orgs/o1/threads/dm"] = { status: 200, body: dm("t2", "b2", "Writer") };
    const result = await actions.createBot(newBot);
    expect(result).toEqual({ ok: true, threadId: "t2" });
    expect(state().bots.map((b) => b.name)).toEqual(["Scout", "Writer"]);
    expect(state().threads.map((t) => t.id)).toEqual(["t1", "t2"]);
  });

  it("createBot explains a refusal and adds nothing", async () => {
    routes["POST /api/v1/orgs/o1/bots"] = { status: 422, body: { detail: "Give the bot a name." } };
    await expect(actions.createBot(newBot)).resolves.toEqual({ ok: false, error: "Give the bot a name." });
    expect(state().bots).toHaveLength(1);
  });

  it("editBot saves on the API and renames its chat, which the API doesn't do yet", async () => {
    routes["PATCH /api/v1/orgs/o1/bots/b1"] = { status: 200, body: { ...scout, name: "Scout Pro", handle: "scout-pro" } };
    await expect(actions.editBot("b1", { name: "Scout Pro" })).resolves.toEqual({ ok: true });
    expect(state().bots[0]).toMatchObject({ name: "Scout Pro", handle: "scout-pro" });
    expect(state().threads[0].title).toBe("Scout Pro");
  });

  it("removeBot deletes it and its chat; a refusal keeps it", async () => {
    routes["DELETE /api/v1/orgs/o1/bots/b1"] = { status: 403, body: { detail: "Only owners and admins can do that." } };
    await expect(actions.removeBot("b1")).resolves.toEqual({ ok: false, error: "Only owners and admins can do that." });
    expect(state().bots).toHaveLength(1);

    routes["DELETE /api/v1/orgs/o1/bots/b1"] = { status: 204 };
    await expect(actions.removeBot("b1")).resolves.toEqual({ ok: true });
    expect(state().bots).toEqual([]);
    expect(state().threads).toEqual([]);
  });

  it("switching org loads that org's bots instead", async () => {
    const globex = { id: "o2", name: "Globex", slug: "globex", plan: "team", role: "member" };
    routes["GET /api/v1/auth/me"] = { status: 200, body: { ...me, organizations: [org, globex] } };
    routes["GET /api/v1/orgs/o2/bots"] = { status: 200, body: [{ ...scout, id: "b9", name: "Globo" }] };
    await actions.restoreSession();
    await actions.switchOrg("o2");
    await vi.waitFor(() => expect(state().bots.map((b) => b.name)).toEqual(["Globo"]));
  });
});

describe("guest mode, even with the API set", () => {
  it("enterGuestMode opens the demo as Ali without calling the API, for this browser session", async () => {
    await actions.enterGuestMode();
    expect(calls).toEqual([]);
    expect(isDemoMode()).toBe(true);
    expect(state()).toMatchObject({ authStatus: "signed-in", guest: true });
    expect(currentUser()?.email).toBe("ali@acme.dev");
    expect(state().bots.some((b) => b.name === "Chief")).toBe(true);
    expect(sessionStorage.getItem("botdesk.guest")).toBe("1");
  });

  it("a reload stays in guest mode", async () => {
    sessionStorage.setItem("botdesk.guest", "1");
    await actions.restoreSession();
    expect(calls).toEqual([]);
    expect(state().guest).toBe(true);
  });

  it("signing out leaves guest mode and throws the demo away: with the API set, no demo data stays", async () => {
    await actions.enterGuestMode();
    await actions.removeBot("b_chief");
    await actions.signOut();
    expect(state()).toMatchObject({ authStatus: "signed-out", guest: false });
    expect(isDemoMode()).toBe(false);
    expect(sessionStorage.getItem("botdesk.guest")).toBeNull();
    expect(state()).toMatchObject({ bots: [], threads: [], messages: [], approvals: [], botsLoading: true });
    expect(calls).toEqual([]);
  });

  it("signing in for real after exploring never mixes in demo data", async () => {
    routes["GET /api/v1/orgs/o1/bots"] = { status: 200, body: [] };
    await actions.enterGuestMode();
    await actions.signIn("zara@example.com", "long-enough");
    expect(state().guest).toBe(false);
    expect(state().org.id).toBe("o1");
    expect(calls).toContain("POST /api/v1/auth/sign-in");
    await vi.waitFor(() => expect(state().botsLoading).toBe(false));
    expect(state().bots).toEqual([]);
  });
});

describe("your profile on the API", () => {
  beforeEach(async () => {
    await actions.signIn("zara@example.com", "long-enough");
  });

  it("updateCurrentUser saves your name and handle as the API answers them", async () => {
    routes["PATCH /api/v1/auth/me"] = { status: 200, body: { ...me, user: { ...me.user, name: "Zara K", handle: "zara-k" } } };
    await expect(actions.updateCurrentUser({ name: "Zara K", handle: "zara-k" })).resolves.toEqual({ ok: true });
    expect(currentUser()).toMatchObject({ name: "Zara K", handle: "zara-k", role: "owner" });
  });

  it("updateCurrentUser explains a taken handle and changes nothing", async () => {
    routes["PATCH /api/v1/auth/me"] = { status: 409, body: { detail: "@omar is taken. Try another." } };
    await expect(actions.updateCurrentUser({ handle: "omar" })).resolves.toEqual({ ok: false, error: "@omar is taken. Try another." });
    expect(currentUser()?.handle).toBe("zara");
  });

  it("changePassword sends both passwords and passes on a refusal", async () => {
    routes["POST /api/v1/auth/change-password"] = { status: 200, body: { message: "Password changed." } };
    await expect(actions.changePassword("old-one", "new-password")).resolves.toEqual({ ok: true });

    routes["POST /api/v1/auth/change-password"] = { status: 401, body: { detail: "Your current password isn't right." } };
    await expect(actions.changePassword("wrong", "new-password")).resolves.toEqual({ ok: false, error: "Your current password isn't right." });
  });
});

/** Stands in for the browser's EventSource, so tests can play a chat's live updates. */
class FakeEventSource {
  static last: FakeEventSource | null = null;
  readonly listeners = new Map<string, (event: MessageEvent<string>) => void>();
  closed = false;
  constructor(
    readonly url: string,
    readonly init?: EventSourceInit,
  ) {
    FakeEventSource.last = this;
  }
  addEventListener(kind: string, listener: (event: MessageEvent<string>) => void) {
    this.listeners.set(kind, listener);
  }
  close() {
    this.closed = true;
  }
  emit(kind: string, event: Record<string, unknown>) {
    const data = JSON.stringify({ id: 1, threadId: "t1", createdAt: "2026-11-12T09:00:01Z", runId: null, kind, ...event });
    this.listeners.get(kind)?.(new MessageEvent(kind, { data }));
  }
}

describe("chats on the API", () => {
  const scout = {
    id: "b1", name: "Scout", handle: "scout", role: "Research", description: "", instructions: "", avatarColor: "sky",
    modelId: "", securityLevel: "ask-before-acting", monthlyBudgetUsd: 50, status: "idle", createdAt: "2026-11-12T08:00:00Z",
  };
  const thread = (id: string, botId: string | null, kind = "dm") => ({
    id, kind, title: kind === "dm" ? "Old name" : "Launch", botId,
    participants: [{ type: "user", id: "u1" }, ...(botId ? [{ type: "bot", id: botId }] : [])],
    lastMessageAt: "2026-11-12T08:00:00Z", lastMessagePreview: "",
  });
  const message = (id: string, text: string, author = { type: "user", id: "u1" }, createdAt = "2026-11-12T09:00:00Z") => ({
    id, threadId: "t1", author, parts: [{ type: "text", text }], status: "complete", createdAt,
  });
  const scoutSays = { type: "bot", id: "b1" };
  const texts = () =>
    state()
      .messages.filter((m) => m.threadId === "t1")
      .map((m) => (m.parts[0]?.type === "text" ? m.parts[0].text : m.parts[0]?.type));

  beforeEach(async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    FakeEventSource.last = null;
    routes["GET /api/v1/orgs/o1/bots"] = { status: 200, body: [scout, { ...scout, id: "b2", name: "Writer" }] };
    routes["GET /api/v1/orgs/o1/threads"] = { status: 200, body: [thread("t1", "b1"), thread("g1", null, "group")] };
    routes["POST /api/v1/orgs/o1/threads/dm"] = { status: 200, body: thread("t2", "b2") };
    routes["GET /api/v1/orgs/o1/threads/t1/messages?limit=50"] = { status: 200, body: [message("m1", "Hi Scout"), message("m2", "Hello!", scoutSays)] };
    await actions.signIn("zara@example.com", "long-enough");
    await vi.waitFor(() => expect(state().botsLoading).toBe(false));
  });

  it("lists your chats, opens a DM for a bot you haven't talked to yet, and names DMs after their bot", () => {
    expect(calls).toContain("POST /api/v1/orgs/o1/threads/dm");
    expect(state().threads.map((t) => [t.id, t.title])).toEqual([["t1", "Scout"], ["g1", "Launch"], ["t2", "Writer"]]);
  });

  it("createGroup starts the group on the API and puts it first in your chats", async () => {
    routes["POST /api/v1/orgs/o1/threads/groups"] = {
      status: 201,
      body: { ...thread("g2", null, "group"), title: "Research", participants: [{ type: "user", id: "u1" }, { type: "user", id: "u2" }, { type: "bot", id: "b1" }] },
    };
    const result = await actions.createGroup({ title: "Research", botIds: ["b1"], userIds: ["u2", "u1"] });

    expect(result).toEqual({ ok: true, threadId: "g2" });
    const request = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/threads/groups"))!;
    // You're added by the API as the creator, so you aren't sent.
    expect(JSON.parse(String(request[1]?.body))).toEqual({ title: "Research", botIds: ["b1"], userIds: ["u2"] });
    expect(state().threads[0]).toMatchObject({ id: "g2", kind: "group", title: "Research" });
  });

  it("createGroup passes on the API's refusal and adds nothing", async () => {
    routes["POST /api/v1/orgs/o1/threads/groups"] = { status: 404, body: { detail: "Some of those people or bots aren't in this organization." } };
    const before = state().threads.length;
    await expect(actions.createGroup({ title: "Research", botIds: ["b9"], userIds: [] })).resolves.toEqual({
      ok: false, error: "Some of those people or bots aren't in this organization.",
    });
    expect(state().threads).toHaveLength(before);
  });

  it("opening a chat loads its messages and follows its live updates; closing stops following", async () => {
    const close = actions.openThread("t1");
    expect(state().threadLoads.t1?.status).toBe("loading");
    await vi.waitFor(() => expect(state().threadLoads.t1).toEqual({ status: "ready", hasOlder: false }));
    expect(texts()).toEqual(["Hi Scout", "Hello!"]);
    expect(FakeEventSource.last?.url).toBe("http://api.test/api/v1/orgs/o1/threads/t1/events");
    expect(FakeEventSource.last?.init).toEqual({ withCredentials: true });
    close();
    expect(FakeEventSource.last?.closed).toBe(true);
  });

  const apiRun = (patch: Record<string, unknown> = {}) => ({
    id: "r1", botId: "b1", threadId: "t1", triggerMessageId: "m1", replyMessageId: null, status: "running", stepsUsed: 1,
    maxSteps: 10, maxSeconds: 300, error: null, createdAt: "2026-11-12T09:00:00Z", startedAt: "2026-11-12T09:00:01Z", finishedAt: null,
    ...patch,
  });

  it("opening a chat where a bot is mid-reply shows it thinking, and follows on from where the list left off", async () => {
    routes["GET /api/v1/orgs/o1/threads/t1/runs?active=true"] = { status: 200, body: { runs: [apiRun()], lastEventId: 42 } };
    actions.openThread("t1");
    await vi.waitFor(() => expect(state().threadLoads.t1?.status).toBe("ready"));
    expect(calls.indexOf("GET /api/v1/orgs/o1/threads/t1/runs?active=true")).toBeLessThan(calls.indexOf("GET /api/v1/orgs/o1/threads/t1/messages?limit=50"));
    expect(FakeEventSource.last?.url).toBe("http://api.test/api/v1/orgs/o1/threads/t1/events?after=42");
    expect(state().messages.at(-1)).toMatchObject({ id: "typing-r1", status: "streaming" });
    expect(state().bots[0]).toMatchObject({ status: "working", statusText: "Thinking…" });
    expect(state().runs).toMatchObject([{ id: "r1", threadId: "t1", botId: "b1" }]);
  });

  it("opening a chat with a stuck run shows the needs-attention notice, which Stop clears", async () => {
    routes["GET /api/v1/orgs/o1/threads/t1/runs?active=true"] = {
      status: 200, body: { runs: [apiRun({ status: "needs_attention", error: "Check the outbox." })], lastEventId: 7 },
    };
    actions.openThread("t1");
    await vi.waitFor(() => expect(state().runs[0]?.status).toBe("needs_attention"));
    expect(state().runs[0].error).toBe("Check the outbox.");
    expect(state().bots[0]).toMatchObject({ status: "error", statusText: "Needs attention" });
    FakeEventSource.last!.emit("run_finished", { runId: "r1", data: { status: "cancelled" } });
    expect(state().runs).toEqual([]);
  });

  it("sendMessage shows your message at once, then the saved one, and knows a bot is replying", async () => {
    actions.openThread("t1");
    await vi.waitFor(() => expect(state().threadLoads.t1?.status).toBe("ready"));
    routes["POST /api/v1/orgs/o1/threads/t1/messages"] = { status: 201, body: { ...message("m3", "Find me leads"), runIds: ["r1"] } };

    actions.sendMessage("t1", "Find me leads");
    expect(texts()).toEqual(["Hi Scout", "Hello!", "Find me leads"]);
    expect(state().threads.find((t) => t.id === "t1")?.lastMessagePreview).toBe("Find me leads");
    await vi.waitFor(() => expect(state().messages.some((m) => m.id === "m3")).toBe(true));
    expect(texts()).toEqual(["Hi Scout", "Hello!", "Find me leads"]);
    expect(state().runs).toEqual([{ id: "r1", threadId: "t1" }]);
  });

  it("a reply streams in: thinking, words, the saved message, done", async () => {
    actions.openThread("t1");
    await vi.waitFor(() => expect(state().threadLoads.t1?.status).toBe("ready"));
    const stream = FakeEventSource.last!;

    stream.emit("run_started", { runId: "r1", data: { botId: "b1" } });
    expect(state().bots.find((b) => b.id === "b1")).toMatchObject({ status: "working", statusText: "Thinking…" });
    expect(state().messages.at(-1)).toMatchObject({ id: "typing-r1", status: "streaming" });

    stream.emit("message_delta", { runId: "r1", data: { messageId: "m9", botId: "b1", text: "On " } });
    stream.emit("message_delta", { runId: "r1", data: { messageId: "m9", botId: "b1", text: "it." } });
    expect(texts()).toEqual(["Hi Scout", "Hello!", "On it."]);
    expect(state().bots.find((b) => b.id === "b1")?.statusText).toBe("Replying…");

    stream.emit("message_saved", { runId: "r1", data: { message: message("m9", "On it.", scoutSays, "2026-11-12T09:00:02Z") } });
    stream.emit("run_finished", { runId: "r1", data: { status: "succeeded" } });
    expect(state().messages.at(-1)).toMatchObject({ id: "m9", status: "complete" });
    expect(state().runs).toEqual([]);
    expect(state().bots.find((b) => b.id === "b1")?.status).toBe("idle");
    expect(state().threads.find((t) => t.id === "t1")?.lastMessagePreview).toBe("On it.");
  });

  it("a message that can't be sent stays, marked with why", async () => {
    routes["POST /api/v1/orgs/o1/threads/t1/messages"] = { status: 404, body: { detail: "Chat not found." } };
    actions.sendMessage("t1", "Anyone there?");
    await vi.waitFor(() => expect(state().messages.at(-1)).toMatchObject({ status: "error", error: "Not sent. Chat not found." }));
  });

  it("stopReplies cancels the runs in progress in that chat", async () => {
    actions.openThread("t1");
    await vi.waitFor(() => expect(state().threadLoads.t1?.status).toBe("ready"));
    FakeEventSource.last!.emit("run_started", { runId: "r1", data: { botId: "b1" } });
    routes["POST /api/v1/orgs/o1/runs/r1/cancel"] = { status: 200, body: {} };
    await expect(actions.stopReplies("t1")).resolves.toEqual({ ok: true });
    expect(calls).toContain("POST /api/v1/orgs/o1/runs/r1/cancel");
  });

  it("loadOlderMessages puts the page before the oldest message at the top", async () => {
    const newest = Array.from({ length: 50 }, (_, i) => message(`n${i}`, `New ${i}`, undefined, `2026-11-12T10:${String(i).padStart(2, "0")}:00Z`));
    routes["GET /api/v1/orgs/o1/threads/t1/messages?limit=50"] = { status: 200, body: newest };
    actions.openThread("t1");
    await vi.waitFor(() => expect(state().threadLoads.t1).toEqual({ status: "ready", hasOlder: true }));

    routes["GET /api/v1/orgs/o1/threads/t1/messages?limit=50&before=2026-11-12T10%3A00%3A00Z"] = { status: 200, body: [message("o1", "Old")] };
    await expect(actions.loadOlderMessages("t1")).resolves.toEqual({ ok: true });
    expect(texts().slice(0, 2)).toEqual(["Old", "New 0"]);
    expect(state().threadLoads.t1).toEqual({ status: "ready", hasOlder: false });
  });
});

describe("approvals on the API", () => {
  const scout = {
    id: "b1", name: "Scout", handle: "scout", role: "Research", description: "", instructions: "", avatarColor: "sky",
    modelId: "", securityLevel: "ask-before-acting", monthlyBudgetUsd: 50, status: "idle", createdAt: "2026-11-12T08:00:00Z",
  };
  const dm = {
    id: "t1", kind: "dm", title: "Scout", botId: "b1", participants: [{ type: "user", id: "u1" }, { type: "bot", id: "b1" }],
    lastMessageAt: "2026-11-12T08:00:00Z", lastMessagePreview: "",
  };
  const approval = (patch: Record<string, unknown> = {}) => ({
    id: "a1", runId: "r1", threadId: "t1", botId: "b1", toolExecutionId: "x1", tool: "demo.send_email",
    title: "Send an email", summary: "Send an email to sara@acme.dev: Launch", riskClass: "external-send",
    reason: "level=Ask before acting · risk=external-send · tainted=no → ask", tainted: false,
    args: { to: "sara@acme.dev", subject: "Launch", body: "" }, finalArgs: null, argsSchema: null,
    preview: [{ label: "To", value: "sara@acme.dev" }], status: "pending",
    requestedAt: "2026-11-12T09:00:01Z", expiresAt: "2026-11-15T09:00:01Z", decidedAt: null, decidedBy: null,
    ...patch,
  });
  const decided = (status: string, patch: Record<string, unknown> = {}) =>
    approval({ status, decidedAt: "2026-11-12T09:05:00Z", decidedBy: { id: "u2", name: "Omar" }, ...patch });
  const stored = () => state().approvals.find((a) => a.id === "a1");
  const body = (path: string) => JSON.parse(String(vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith(path))![1]?.body));

  beforeEach(async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    routes["GET /api/v1/orgs/o1/bots"] = { status: 200, body: [scout] };
    routes["GET /api/v1/orgs/o1/threads"] = { status: 200, body: [dm] };
    routes["GET /api/v1/orgs/o1/threads/t1/messages?limit=50"] = { status: 200, body: [] };
    routes["GET /api/v1/orgs/o1/approvals?status=all"] = { status: 200, body: [approval()] };
    routes["GET /api/v1/orgs/o1/approvals?status=pending"] = { status: 200, body: [approval()] };
    await actions.signIn("zara@example.com", "long-enough");
    await vi.waitFor(() => expect(state().botsLoading).toBe(false));
  });

  it("loadApprovals fills the Approvals page from the list", async () => {
    await expect(actions.loadApprovals()).resolves.toEqual({ ok: true });
    expect(stored()).toMatchObject({ status: "pending", runId: "r1", riskClass: "external-send", expiresAt: "2026-11-15T09:00:01Z" });
  });

  it("approving sends the decision and shows who decided", async () => {
    await actions.loadApprovals();
    routes["POST /api/v1/orgs/o1/approvals/a1/decide"] = { status: 200, body: decided("approved", { decidedBy: { id: "u1", name: "Zara" } }) };
    await expect(actions.decideApproval("a1", "approve")).resolves.toEqual({ ok: true });
    expect(body("/approvals/a1/decide")).toEqual({ decision: "approve" });
    expect(stored()).toMatchObject({ status: "approved", decidedBy: "u1", decidedByName: "Zara" });
  });

  it("an edit sends the edited arguments", async () => {
    await actions.loadApprovals();
    const editedArgs = { to: "sara@acme.dev", subject: "Launch day", body: "" };
    routes["POST /api/v1/orgs/o1/approvals/a1/decide"] = { status: 200, body: decided("edited", { finalArgs: editedArgs }) };
    await actions.decideApproval("a1", "approve", editedArgs);
    expect(body("/approvals/a1/decide")).toEqual({ decision: "approve", editedArgs });
    expect(stored()).toMatchObject({ status: "edited", finalArgs: editedArgs });
  });

  it("409: someone decided first, so the approval is fetched again and the card shows what happened", async () => {
    await actions.loadApprovals();
    routes["POST /api/v1/orgs/o1/approvals/a1/decide"] = { status: 409, body: { detail: "This approval was already decided." } };
    routes["GET /api/v1/orgs/o1/approvals/a1"] = { status: 200, body: decided("denied") };
    await expect(actions.decideApproval("a1", "approve")).resolves.toEqual({
      ok: false, error: "This approval was already decided.", reason: "conflict", status: "denied",
    });
    expect(stored()).toMatchObject({ status: "denied", decidedByName: "Omar" });
  });

  it("409 while it still waits (the tool went away) isn't a conflict, so an edit can be kept", async () => {
    await actions.loadApprovals();
    routes["POST /api/v1/orgs/o1/approvals/a1/decide"] = { status: 409, body: { detail: "This tool isn't available any more." } };
    routes["GET /api/v1/orgs/o1/approvals/a1"] = { status: 200, body: approval() };
    await expect(actions.decideApproval("a1", "approve", { to: "sara@acme.dev" })).resolves.toEqual({
      ok: false, error: "This tool isn't available any more.", status: "pending",
    });
    expect(stored()?.status).toBe("pending");
  });

  it("400: the edited arguments don't fit, and nothing changes", async () => {
    await actions.loadApprovals();
    const detail = "Those changes don't fit this action: to: value is not a valid email address";
    routes["POST /api/v1/orgs/o1/approvals/a1/decide"] = { status: 400, body: { detail } };
    await expect(actions.decideApproval("a1", "approve", { to: "nope", subject: "Launch" })).resolves.toEqual({ ok: false, error: detail, reason: "invalid" });
    expect(stored()?.status).toBe("pending");
  });

  it("refreshPendingApprovals adds new requests and re-checks ones decided elsewhere", async () => {
    await actions.refreshPendingApprovals();
    expect(stored()?.status).toBe("pending");

    routes["GET /api/v1/orgs/o1/approvals?status=pending"] = { status: 200, body: [approval({ id: "a2" })] };
    routes["GET /api/v1/orgs/o1/approvals/a1"] = { status: 200, body: decided("expired", { decidedBy: null }) };
    await actions.refreshPendingApprovals();
    expect(stored()?.status).toBe("expired");
    expect(state().approvals.filter((a) => a.status === "pending").map((a) => a.id)).toEqual(["a2"]);
  });

  it("opening a chat with a waiting approval shows its card and the bot waiting", async () => {
    routes["GET /api/v1/orgs/o1/approvals?status=all&threadId=t1"] = { status: 200, body: [approval()] };
    actions.openThread("t1");
    await vi.waitFor(() => expect(state().threadLoads.t1?.status).toBe("ready"));
    expect(state().messages.at(-1)).toMatchObject({ id: "typing-r1", parts: [{ type: "approval", approvalId: "a1" }, { type: "text", text: "" }] });
    expect(state().bots[0]).toMatchObject({ status: "waiting-approval", statusText: "Waiting for approval" });
  });

  it("a slow pending list after you approved doesn't bring the buttons back", async () => {
    await actions.loadApprovals();
    routes["POST /api/v1/orgs/o1/approvals/a1/decide"] = { status: 200, body: decided("approved", { decidedBy: { id: "u1", name: "Zara" } }) };
    await actions.decideApproval("a1", "approve");
    await actions.refreshPendingApprovals(); // still answers with the pending copy
    await actions.loadApprovals();
    expect(stored()?.status).toBe("approved");
  });

  it("opening a chat whose waiting approval's run has ended doesn't leave a run waiting", async () => {
    routes["GET /api/v1/orgs/o1/approvals?status=all&threadId=t1"] = { status: 200, body: [approval()] };
    routes["GET /api/v1/orgs/o1/threads/t1/runs?active=true"] = { status: 200, body: { runs: [], lastEventId: 3 } };
    actions.openThread("t1");
    await vi.waitFor(() => expect(state().threadLoads.t1?.status).toBe("ready"));
    expect(state().runs).toEqual([]);
    expect(state().bots[0]).toMatchObject({ status: "idle" });
  });

  it("live: a request pauses the bot, a decision resumes it, needs-attention can be stopped", async () => {
    actions.openThread("t1");
    await vi.waitFor(() => expect(state().threadLoads.t1?.status).toBe("ready"));
    const stream = FakeEventSource.last!;

    stream.emit("run_started", { runId: "r1", data: { botId: "b1" } });
    stream.emit("approval_requested", { runId: "r1", data: { approval: approval() } });
    expect(stored()?.status).toBe("pending");
    expect(state().bots[0]).toMatchObject({ status: "waiting-approval", statusText: "Waiting for approval" });
    // The sidebar count is refreshed at once too.
    await vi.waitFor(() => expect(calls).toContain("GET /api/v1/orgs/o1/approvals?status=pending"));

    stream.emit("approval_decided", { runId: "r1", data: { approval: decided("approved") } });
    stream.emit("run_resumed", { runId: "r1", data: { botId: "b1" } });
    expect(stored()?.status).toBe("approved");
    expect(state().bots[0]).toMatchObject({ status: "working", statusText: "Thinking…" });

    stream.emit("run_needs_attention", { runId: "r1", data: { status: "needs_attention", error: "Check the outbox." } });
    expect(state().bots[0]).toMatchObject({ status: "error", statusText: "Needs attention" });
    routes["POST /api/v1/orgs/o1/runs/r1/cancel"] = { status: 200, body: {} };
    await expect(actions.stopRun("r1")).resolves.toEqual({ ok: true });

    stream.emit("run_finished", { runId: "r1", data: { status: "cancelled" } });
    expect(state().bots[0]).toMatchObject({ status: "idle" });
  });
});
