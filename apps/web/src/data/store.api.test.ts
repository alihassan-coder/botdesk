import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot as state } from "./store";

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
