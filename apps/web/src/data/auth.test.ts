import { describe, expect, it } from "vitest";
import { actions, getStoreSnapshot as state } from "./store";

const SESSION_KEY = "botdesk.session";

describe("signIn", () => {
  it("signs in with the right email and password, and remembers the session", async () => {
    expect(await actions.signIn("Sara@Acme.dev ", "botdesk123")).toEqual({ ok: true });
    expect(state().authStatus).toBe("signed-in");
    expect(state().currentUserId).toBe("u_sara");
    expect(JSON.parse(localStorage.getItem(SESSION_KEY)!).user.id).toBe("u_sara");
  });

  it("gives the same message for a wrong password and an unknown email", async () => {
    const wrongPassword = await actions.signIn("ali@acme.dev", "nope");
    const unknownEmail = await actions.signIn("nobody@acme.dev", "botdesk123");
    expect(wrongPassword).toEqual({ ok: false, error: "That email and password don't match." });
    expect(unknownEmail).toEqual(wrongPassword);
    expect(state().authStatus).not.toBe("signed-in");
  });
});

describe("signUp", () => {
  it("creates the account and signs you in", async () => {
    expect(await actions.signUp({ name: "Zara Ahmed", email: "Zara@Acme.dev", password: "long-enough" })).toEqual({ ok: true });
    const me = state().users.find((u) => u.id === state().currentUserId);
    expect(me).toMatchObject({ name: "Zara Ahmed", email: "zara@acme.dev", handle: "zara-ahmed" });
    expect(state().authStatus).toBe("signed-in");
  });

  it("then lets you sign in with that password", async () => {
    await actions.signUp({ name: "Zara", email: "zara@acme.dev", password: "long-enough" });
    await actions.signOut();
    expect(await actions.signIn("zara@acme.dev", "long-enough")).toEqual({ ok: true });
  });

  it("refuses an email that already has an account, and short passwords", async () => {
    expect(await actions.signUp({ name: "Ali", email: "ali@acme.dev", password: "long-enough" })).toMatchObject({ ok: false });
    expect(await actions.signUp({ name: "New", email: "new@acme.dev", password: "short" })).toEqual({
      ok: false,
      error: "Use at least 8 characters for your password.",
    });
  });
});

describe("sessions", () => {
  it("restoreSession signs you back in from a saved session, even a newly created account", async () => {
    const zara = { id: "u_zara", name: "Zara", email: "zara@acme.dev", handle: "zara", role: "admin", presence: "online" };
    localStorage.setItem(SESSION_KEY, JSON.stringify({ user: zara }));
    await actions.restoreSession();
    expect(state().authStatus).toBe("signed-in");
    expect(state().currentUserId).toBe("u_zara");
  });

  it("restoreSession marks you signed out when nothing is saved", async () => {
    await actions.restoreSession();
    expect(state().authStatus).toBe("signed-out");
  });

  it("signOut forgets the session", async () => {
    await actions.signIn("ali@acme.dev", "botdesk123");
    await actions.signOut();
    expect(state().authStatus).toBe("signed-out");
    expect(localStorage.getItem(SESSION_KEY)).toBeNull();
  });
});
