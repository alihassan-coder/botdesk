"use client";

/**
 * Client-side data store for the UI.
 *
 * Two modes, picked by NEXT_PUBLIC_API_URL:
 * - Set: sign-in, your organizations, their members, invitations and bots come from
 *   apps/api (see `./api`). Chats aren't on the API yet: each bot gets an empty chat,
 *   and the demo's threads, approvals, routines and memories are left out.
 * - Not set (tests, e2e, demos): everything is the in-memory mock, with fake bot replies.
 * Guest mode ("Explore the demo") uses the mock in either case, so people can look
 * around without an account; it never calls the API.
 * Screens can't tell the difference: they use the hooks and actions below either way.
 */
import { useCallback, useRef, useSyncExternalStore } from "react";
import { makeHandle } from "@/lib/handle";
import { parseMentions } from "@/lib/mentions";
import { authApi, botApi, inviteApi, orgApi } from "./api/botdesk";
import { ApiError, apiBaseUrl } from "./api/client";
import { toApiBot, toBot, toInvitation, toOrg, toUser } from "./api/map";
import type { ApiMe } from "./api/types";
import * as mock from "./mock/fixtures";
import type { Approval, ApprovalStatus, Bot, Invitation, Membership, Message, Org, Participant, ProviderCredential, Routine, Thread, User } from "./types";

/** What you fill in to create a bot; the rest (id, handle, status…) is filled in for you. */
export type NewBotInput = Pick<
  Bot,
  "name" | "role" | "description" | "avatarColor" | "modelId" | "securityLevel" | "computerMode" | "instructions" | "monthlyBudgetUsd"
>;

/** What you fill in to create a routine. */
export type NewRoutineInput = Pick<Routine, "botId" | "name" | "description" | "schedule" | "steps" | "enabled">;

/** "unknown" until the browser has checked for a saved session (first render, server). */
export type AuthStatus = "unknown" | "signed-in" | "signed-out";

/** What an action that can fail returns: screens show `error` as is. */
export type ActionResult = { ok: true } | { ok: false; error: string };

/** True when the mock data is in use: there's no API to talk to, or you're a guest. */
export const isDemoMode = () => apiBaseUrl() === "" || state.guest;

interface State {
  /** The current organization: everything below belongs to it. */
  org: typeof mock.org;
  /** Every organization you belong to, for the org switcher. */
  orgs: Membership[];
  users: typeof mock.users;
  /** Invites sent but not yet accepted. API only: in the mock, invites join at once. */
  invitations: Invitation[];
  currentUserId: string;
  authStatus: AuthStatus;
  /** Exploring the demo without an account. Nothing is saved, and the API is never called. */
  guest: boolean;
  /** MOCK: email → password. Replaced by Better Auth on the API. */
  passwords: Record<string, string>;
  bots: Bot[];
  /** True while the current org's bots are on their way from the API. */
  botsLoading: boolean;
  threads: Thread[];
  messages: Message[];
  approvals: Approval[];
  connectors: typeof mock.connectors;
  connections: typeof mock.connections;
  routines: typeof mock.routines;
  models: typeof mock.models;
  credentials: typeof mock.credentials;
  memories: typeof mock.memories;
  usage: typeof mock.usage;
  templates: typeof mock.templates;
}

function seed(): State {
  return {
    org: mock.org,
    orgs: [{ ...mock.org, role: mock.users.find((u) => u.id === mock.currentUserId)!.role }],
    users: mock.users,
    invitations: [],
    currentUserId: mock.currentUserId,
    authStatus: "unknown",
    guest: false,
    passwords: mock.mockPasswords,
    bots: mock.bots,
    botsLoading: false,
    threads: mock.threads,
    messages: mock.messages,
    approvals: mock.approvals,
    connectors: mock.connectors,
    connections: mock.connections,
    routines: mock.routines,
    models: mock.models,
    credentials: mock.credentials,
    memories: mock.memories,
    usage: mock.usage,
    templates: mock.templates,
  };
}

let state: State = seed();
const listeners = new Set<() => void>();

function set(updater: (s: State) => State) {
  state = updater(state);
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

const getSnapshot = () => state;
const getServerSnapshot = () => state;

/** The whole state, read once. For tests and debugging only: screens use the hooks below. */
export const getStoreSnapshot = () => state;

function shallowEqual(a: unknown, b: unknown) {
  if (Object.is(a, b)) return true;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  return false;
}

/**
 * Subscribe to a slice of state. Selectors may return new arrays (e.g. `filter`);
 * results are shallow-compared so components only re-render when the slice changes.
 */
export function useStore<T>(selector: (s: State) => T): T {
  const last = useRef<{ value: T } | null>(null);
  const read = useCallback(
    (s: State) => {
      const next = selector(s);
      if (last.current && shallowEqual(last.current.value, next)) return last.current.value;
      last.current = { value: next };
      return next;
    },
    [selector],
  );
  return useSyncExternalStore(
    subscribe,
    () => read(getSnapshot()),
    () => read(getServerSnapshot()),
  );
}

const id = () => Math.random().toString(36).slice(2, 10);
const now = () => new Date().toISOString();


/* ---------- Session ----------
 * On the API the session is an httpOnly cookie the browser sends for us. In the mock,
 * the signed-in user is remembered in localStorage instead.
 */
const SESSION_KEY = "botdesk.session";

function saveMockSession(user: User | null) {
  try {
    if (user) localStorage.setItem(SESSION_KEY, JSON.stringify({ user }));
    else localStorage.removeItem(SESSION_KEY);
  } catch {}
}

function startMockSession(user: User) {
  set((st) => ({
    ...st,
    users: st.users.some((u) => u.id === user.id) ? st.users : [...st.users, user],
    currentUserId: user.id,
    authStatus: "signed-in",
  }));
  saveMockSession(user);
}

/** The API's message when it has one; screens show it to people as is. */
function failure(error: unknown): { ok: false; error: string } {
  return { ok: false, error: error instanceof ApiError ? error.message : "Something went wrong. Try again." };
}

/* The organization you last chose is remembered per browser, like Slack and Linear do. */
const ORG_KEY = "botdesk.org";

function rememberOrg(orgId: string) {
  try {
    localStorage.setItem(ORG_KEY, orgId);
  } catch {}
}

function rememberedOrgId() {
  try {
    return localStorage.getItem(ORG_KEY);
  } catch {
    return null;
  }
}

/** Signed in on the API: you, in the organization you used last here (else your first). */
function startApiSession(me: ApiMe) {
  const orgs: Membership[] = me.organizations;
  const org = orgs.find((o) => o.id === rememberedOrgId()) ?? orgs[0];
  const user = toUser(me.user, org?.role ?? "member");
  set((st) => ({ ...st, orgs, users: [user], invitations: [], currentUserId: user.id, authStatus: "signed-in" }));
  if (org) enterOrg(org);
}

/**
 * Makes `org` the current organization: drops what belonged to the previous one,
 * then loads this one's people. Until they arrive, the member list shows only you.
 */
function enterOrg(org: Membership) {
  rememberOrg(org.id);
  set((st) => ({
    ...st,
    org: toOrg(org),
    users: st.users.filter((u) => u.id === st.currentUserId).map((u) => ({ ...u, role: org.role })),
    invitations: [],
    // The demo's chats, approvals, routines and memories belong to the demo bots, not to this org.
    ...withBots(st, []),
    messages: [],
    approvals: [],
    routines: [],
    memories: [],
    botsLoading: true,
  }));
  void loadOrgPeople(org);
  void loadBots(org);
}

async function loadBots(org: Membership) {
  const bots = await botApi.list(org.id).catch(() => null);
  set((st) => {
    if (st.org.id !== org.id) return st; // switched org while loading
    return { ...st, ...withBots(st, bots?.map(toBot) ?? []), botsLoading: false };
  });
}

/*
 * Chats aren't on the API yet. So every real bot gets an empty DM here, which
 * keeps it in the sidebar and gives its details a page; the chat says "coming soon".
 */
const dmId = (botId: string) => `dm-${botId}`;

function dmFor(bot: Bot, userId: string): Thread {
  return {
    id: dmId(bot.id), kind: "dm", title: bot.name, botId: bot.id,
    participants: [{ type: "user", id: userId }, { type: "bot", id: bot.id }],
    lastMessageAt: bot.createdAt, lastMessagePreview: bot.role || "Just hired", unread: 0,
  };
}

/** API mode: the bots, and one empty chat for each. */
function withBots(st: State, bots: Bot[]): Pick<State, "bots" | "threads"> {
  return { bots, threads: bots.map((b) => dmFor(b, st.currentUserId)) };
}

/** Members, plus pending invites for admins. */
async function loadOrgPeople(org: Membership) {
  const canManage = org.role !== "member";
  const [members, invitations] = await Promise.all([
    orgApi.members(org.id).catch(() => null),
    canManage ? inviteApi.list(org.id).catch(() => null) : Promise.resolve([]),
  ]);
  set((st) => {
    if (st.org.id !== org.id) return st; // signed out or switched org while loading
    const users = members?.map((m) => toUser(m, m.role)) ?? st.users;
    const me = st.users.find((u) => u.id === st.currentUserId);
    return {
      ...st,
      users: me && !users.some((u) => u.id === me.id) ? [me, ...users] : users,
      invitations: invitations?.map(toInvitation) ?? st.invitations,
    };
  });
}

/* ---------- Guest mode ----------
 * A guest is Ali in the demo team, for this browser session only (sessionStorage), so a
 * reload keeps you exploring but closing the tab ends it. Entering and leaving both start
 * from fresh mock data, so a real account never sees demo data or the other way round.
 */
const GUEST_KEY = "botdesk.guest";

function rememberGuest(isGuest: boolean) {
  try {
    if (isGuest) sessionStorage.setItem(GUEST_KEY, "1");
    else sessionStorage.removeItem(GUEST_KEY);
  } catch {}
}

function wasGuest() {
  try {
    return sessionStorage.getItem(GUEST_KEY) === "1";
  } catch {
    return false;
  }
}

function startGuestSession() {
  cancelMockTimers();
  set(() => ({ ...seed(), guest: true, authStatus: "signed-in" }));
  rememberGuest(true);
}

function leaveGuestMode() {
  cancelMockTimers();
  set(() => seed());
  rememberGuest(false);
}

/* restoreSession can be asked for twice at once (auth gate + sign-in page); share one request. */
let restoring: Promise<void> | null = null;

const mockAuth = {
  restoreSession() {
    try {
      const saved = JSON.parse(localStorage.getItem(SESSION_KEY) ?? "null") as { user?: User; userId?: string } | null;
      const user = saved?.user ?? state.users.find((u) => u.id === saved?.userId);
      if (user) return startMockSession(user);
    } catch {}
    set((st) => ({ ...st, authStatus: "signed-out" }));
  },

  signIn(email: string, password: string): ActionResult {
    const user = state.users.find((u) => u.email.toLowerCase() === email.trim().toLowerCase());
    if (!user || state.passwords[user.email] !== password) return { ok: false, error: "That email and password don't match." };
    startMockSession(user);
    return { ok: true };
  },

  signUp(input: { name: string; email: string; password: string }): ActionResult {
    const email = input.email.trim().toLowerCase();
    if (state.users.some((u) => u.email.toLowerCase() === email)) return { ok: false, error: "An account with this email already exists. Sign in instead." };
    if (input.password.length < 8) return { ok: false, error: "Use at least 8 characters for your password." };

    const user: User = {
      id: `u_${id()}`, name: input.name.trim(), email,
      handle: makeHandle(input.name, [...state.users.map((u) => u.handle), ...state.bots.map((b) => b.handle)]),
      role: "admin", presence: "online",
    };
    set((st) => ({ ...st, passwords: { ...st.passwords, [email]: input.password } }));
    startMockSession(user);
    return { ok: true };
  },
};

/*
 * Auth actions are async because the API is. In the mock they finish before their first
 * `await`, so the state is already updated when the call returns.
 */
const authActions = {
  /** Called once when the app loads: are we already signed in on this device? */
  async restoreSession(): Promise<void> {
    if (wasGuest()) return startGuestSession();
    if (isDemoMode()) return mockAuth.restoreSession();
    restoring ??= authApi
      .me()
      .then(startApiSession, () => set((st) => ({ ...st, authStatus: "signed-out" })))
      .finally(() => (restoring = null));
    return restoring;
  },

  /** "Explore the demo": look around as Ali in the demo team, without an account. */
  async enterGuestMode(): Promise<void> {
    startGuestSession();
  },

  async signIn(email: string, password: string): Promise<ActionResult> {
    if (state.guest) leaveGuestMode();
    if (isDemoMode()) return mockAuth.signIn(email, password);
    try {
      startApiSession(await authApi.signIn(email.trim(), password));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  async signUp(input: { name: string; email: string; password: string }): Promise<ActionResult> {
    if (state.guest) leaveGuestMode();
    if (isDemoMode()) return mockAuth.signUp(input);
    try {
      startApiSession(await authApi.signUp({ ...input, name: input.name.trim(), email: input.email.trim() }));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  async signOut(): Promise<void> {
    if (state.guest) {
      leaveGuestMode();
      return set((st) => ({ ...st, authStatus: "signed-out" }));
    }
    if (isDemoMode()) saveMockSession(null);
    // Signed out here even if the API can't be reached; the cookie expires on its own.
    else await authApi.signOut().catch(() => {});
    set((st) => ({ ...st, authStatus: "signed-out" }));
  },

  /** Ask for a reset link. The answer never says whether the email has an account. */
  async requestPasswordReset(email: string): Promise<ActionResult> {
    if (isDemoMode()) return { ok: true }; // MOCK: nothing is sent.
    try {
      await authApi.forgotPassword(email.trim());
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Join the organization an invite link is for, and switch to it. API only. */
  async acceptInvitation(token: string): Promise<ActionResult> {
    if (isDemoMode()) return { ok: false, error: "Invite links work once botdesk is connected to its API." };
    try {
      const org = await inviteApi.accept(token);
      set((st) => ({ ...st, orgs: [...st.orgs.filter((o) => o.id !== org.id), org] }));
      enterOrg(org);
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },
};

/* ---------- Organization and members ---------- */

const orgActions = {
  /** Open another of your organizations. Its members, invites and bots replace the current ones. */
  async switchOrg(orgId: string): Promise<void> {
    const org = state.orgs.find((o) => o.id === orgId);
    if (!org || org.id === state.org.id || isDemoMode()) return;
    enterOrg(org);
  },

  async updateOrg(patch: Partial<Pick<Org, "name" | "slug">>): Promise<ActionResult> {
    if (isDemoMode()) {
      set((st) => ({ ...st, org: { ...st.org, ...patch }, orgs: st.orgs.map((o) => (o.id === st.org.id ? { ...o, ...patch } : o)) }));
      return { ok: true };
    }
    try {
      const saved = await orgApi.update(state.org.id, patch);
      set((st) => ({ ...st, org: toOrg(saved), orgs: st.orgs.map((o) => (o.id === saved.id ? saved : o)) }));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /**
   * On the API this creates an invite and returns its link to share (no emails yet).
   * MOCK: adds the invited person straight away.
   */
  async inviteMember(email: string, role: User["role"]): Promise<ActionResult & { inviteUrl?: string }> {
    if (isDemoMode()) {
      const name = email.split("@")[0].replace(/[._-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
      const handle = makeHandle(name, state.users.map((u) => u.handle));
      set((st) => ({ ...st, users: [...st.users, { id: `u_${id()}`, name, email, handle, role, presence: "offline" }] }));
      return { ok: true };
    }
    try {
      // Owners are made from existing members, never by invite.
      const invite = await inviteApi.create(state.org.id, { email, role: role === "owner" ? "admin" : role });
      set((st) => ({ ...st, invitations: [...st.invitations.filter((i) => i.id !== invite.id), toInvitation(invite)] }));
      return { ok: true, inviteUrl: invite.inviteUrl };
    } catch (error) {
      return failure(error);
    }
  },

  async revokeInvitation(invitationId: string): Promise<ActionResult> {
    try {
      if (!isDemoMode()) await inviteApi.revoke(state.org.id, invitationId);
      set((st) => ({ ...st, invitations: st.invitations.filter((i) => i.id !== invitationId) }));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  async changeMemberRole(userId: string, role: User["role"]): Promise<ActionResult> {
    try {
      const saved = isDemoMode() ? role : (await orgApi.changeRole(state.org.id, userId, role)).role;
      set((st) => ({ ...st, users: st.users.map((u) => (u.id === userId ? { ...u, role: saved } : u)) }));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  async removeMember(userId: string): Promise<ActionResult> {
    try {
      if (!isDemoMode()) await orgApi.removeMember(state.org.id, userId);
      set((st) => ({ ...st, users: st.users.filter((u) => u.id !== userId) }));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },
};

export const actions = {
  ...authActions,
  ...orgActions,

  sendMessage(threadId: string, text: string) {
    const s = state;
    const mentions = parseMentions(text, s.bots, s.users);

    const msg: Message = {
      id: id(),
      threadId,
      author: { type: "user", id: s.currentUserId },
      parts: [{ type: "text", text }],
      createdAt: now(),
      mentions,
    };
    set((st) => ({
      ...st,
      messages: [...st.messages, msg],
      threads: st.threads.map((t) =>
        t.id === threadId ? { ...t, lastMessageAt: msg.createdAt, lastMessagePreview: text } : t,
      ),
    }));

    // MOCK: pick who replies. In a DM it's always that bot (it can hand work off to others);
    // in a group it's the first bot you mentioned, else the first bot in the group.
    const thread = s.threads.find((t) => t.id === threadId);
    const replyBotId =
      thread?.kind === "dm"
        ? thread.botId
        : (mentions.find((m) => m.type === "bot")?.id ?? thread?.participants.find((p) => p.type === "bot")?.id);
    if (replyBotId) fakeBotReply(threadId, replyBotId, text);
  },

  decideApproval(approvalId: string, status: Extract<ApprovalStatus, "approved" | "denied">) {
    set((st) => ({
      ...st,
      approvals: st.approvals.map((a) =>
        a.id === approvalId ? { ...a, status, decidedBy: st.currentUserId, decidedAt: now() } : a,
      ),
    }));
    const a = state.approvals.find((x) => x.id === approvalId);
    if (!a) return;

    // Keep the bot's status honest: how many decisions does it still need from you?
    const stillWaiting = state.approvals.filter((x) => x.botId === a.botId && x.status === "pending").length;
    actions.updateBot(
      a.botId,
      stillWaiting > 0
        ? { status: "waiting-approval", statusText: `${stillWaiting} waiting for you` }
        : { status: "idle", statusText: "All caught up" },
    );

    // MOCK: the bot confirms. Real bots report the actual result of the action.
    const text = status === "approved" ? `Done: ${a.title}.` : `Okay, I won't go ahead with “${a.title}”.`;
    later(() => pushBotMessage(a.threadId, a.botId, [{ type: "text", text }]), 700);
  },

  /** The member changed the action's details (e.g. the email body), then approved it. */
  editAndApprove(approvalId: string, preview: Approval["preview"]) {
    set((st) => ({
      ...st,
      approvals: st.approvals.map((a) => (a.id === approvalId ? { ...a, preview } : a)),
    }));
    actions.decideApproval(approvalId, "approved");
  },

  answerQuestion(messageId: string, answer: string) {
    set((st) => ({
      ...st,
      messages: st.messages.map((m) =>
        m.id === messageId
          ? { ...m, parts: m.parts.map((p) => (p.type === "question" ? { ...p, answered: answer } : p)) }
          : m,
      ),
    }));
  },

  markRead(threadId: string) {
    set((st) => ({ ...st, threads: st.threads.map((t) => (t.id === threadId ? { ...t, unread: 0 } : t)) }));
  },

  updateBot(botId: string, patch: Partial<Bot>) {
    set((st) => ({ ...st, bots: st.bots.map((b) => (b.id === botId ? { ...b, ...patch } : b)) }));
  },

  toggleRoutine(routineId: string) {
    set((st) => ({
      ...st,
      routines: st.routines.map((r) => (r.id === routineId ? { ...r, enabled: !r.enabled } : r)),
    }));
  },

  deleteMemory(memoryId: string) {
    set((st) => ({ ...st, memories: st.memories.filter((m) => m.id !== memoryId) }));
  },

  /**
   * Creates a bot and its DM, and returns the DM's id so the screen can open it.
   * MOCK: the bot speaks first, so the chat never opens empty.
   */
  async createBot(input: NewBotInput): Promise<ActionResult & { threadId?: string }> {
    if (isDemoMode()) return { ok: true, threadId: createMockBot(input) };
    try {
      const bot = toBot(await botApi.create(state.org.id, toApiBot(input)));
      set((st) => ({ ...st, ...withBots(st, [...st.bots, bot]) }));
      return { ok: true, threadId: dmId(bot.id) };
    } catch (error) {
      return failure(error);
    }
  },

  /** Hire a ready-made bot from the marketplace, with safe defaults. */
  async createBotFromTemplate(templateId: string): Promise<ActionResult & { threadId?: string }> {
    const t = state.templates.find((x) => x.id === templateId);
    if (!t) return { ok: false, error: "That bot isn't in the marketplace any more." };
    return actions.createBot({
      name: t.name, role: t.role, description: t.description, avatarColor: t.avatarColor,
      modelId: "m_claude", securityLevel: "ask-before-acting", computerMode: "own",
      instructions: "", monthlyBudgetUsd: 20,
    });
  },

  /** Change a bot's profile, model, limits or instructions. */
  async editBot(botId: string, patch: Partial<NewBotInput>): Promise<ActionResult> {
    if (isDemoMode()) {
      actions.updateBot(botId, patch);
      return { ok: true };
    }
    try {
      const saved = toBot(await botApi.update(state.org.id, botId, toApiBot(patch)));
      set((st) => ({ ...st, ...withBots(st, st.bots.map((b) => (b.id === botId ? saved : b))) }));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Remove a bot (owners and admins), with its DM and anything waiting on it. */
  async removeBot(botId: string): Promise<ActionResult> {
    try {
      if (!isDemoMode()) await botApi.remove(state.org.id, botId);
    } catch (error) {
      return failure(error);
    }
    set((st) => {
      // It leaves its groups too; a group with no bots left has no one to talk to, so it goes.
      const threads = st.threads
        .filter((t) => !(t.kind === "dm" && t.botId === botId))
        .map((t) => ({ ...t, participants: t.participants.filter((p) => !(p.type === "bot" && p.id === botId)) }))
        .filter((t) => t.participants.some((p) => p.type === "bot"));
      const kept = new Set(threads.map((t) => t.id));
      return {
        ...st,
        bots: st.bots.filter((b) => b.id !== botId),
        threads,
        messages: st.messages.filter((m) => kept.has(m.threadId)),
        approvals: st.approvals.filter((a) => a.botId !== botId),
        routines: st.routines.filter((r) => r.botId !== botId),
      };
    });
    return { ok: true };
  },

  /** Saves a routine and has its bot confirm in their chat, the way it would after "do this every week". */
  createRoutine(input: NewRoutineInput) {
    const routineId = `r_${id()}`;
    set((st) => ({ ...st, routines: [...st.routines, { ...input, id: routineId, source: "edit" }] }));
    const thread = state.threads.find((t) => t.kind === "dm" && t.botId === input.botId);
    if (thread) {
      pushBotMessage(thread.id, input.botId, [
        { type: "routine-created", routineId, name: input.name },
        { type: "text", text: `Got it. I'll run “${input.name}” ${input.schedule.charAt(0).toLowerCase()}${input.schedule.slice(1)}.` },
      ]);
    }
    return routineId;
  },

  updateCurrentUser(patch: Partial<Pick<User, "name" | "handle">>) {
    set((st) => ({ ...st, users: st.users.map((u) => (u.id === st.currentUserId ? { ...u, ...patch } : u)) }));
  },

  addCredential(input: Pick<ProviderCredential, "provider" | "label" | "owner" | "baseUrl"> & { key: string }) {
    const { key, ...rest } = input;
    const maskedKey = key.length > 8 ? `${key.slice(0, 4)}…${key.slice(-4)}` : "••••";
    set((st) => ({ ...st, credentials: [...st.credentials, { ...rest, id: `k_${id()}`, maskedKey }] }));
  },

  removeCredential(credentialId: string) {
    set((st) => ({ ...st, credentials: st.credentials.filter((k) => k.id !== credentialId) }));
  },

  /** MOCK: connecting an app (OAuth for Gmail, a URL for MCP) succeeds at once. */
  connectApp(connectorId: string, account: string) {
    set((st) => ({
      ...st,
      connections: [...st.connections, { id: `c_${id()}`, connectorId, account, owner: "user", status: "connected", connectedAt: now() }],
    }));
  },

  disconnectApp(connectionId: string) {
    set((st) => ({ ...st, connections: st.connections.filter((c) => c.id !== connectionId) }));
  },

  /** Back to the original mock data. Also cancels bot replies still in progress, so none land afterwards. */
  reset() {
    cancelMockTimers();
    restoring = null;
    set(() => seed());
  },
};

/** MOCK: a new bot and its DM, where it says hello first. Returns the DM's id. */
function createMockBot(input: NewBotInput) {
  const botId = `b_${id()}`;
  const threadId = `t_${id()}`;
  const handle = makeHandle(input.name, [...state.bots.map((b) => b.handle), ...state.users.map((u) => u.handle)]);
  const hello = `Hi! I'm ${input.name}. ${input.description || input.role} What should I work on first?`;

  set((st) => ({
    ...st,
    bots: [
      ...st.bots,
      { ...input, id: botId, handle, status: "idle", statusText: "Just hired", connectionIds: [], createdAt: now(), spentThisMonthUsd: 0 },
    ],
    threads: [
      {
        id: threadId, kind: "dm", title: input.name, botId,
        participants: [{ type: "user", id: st.currentUserId }, { type: "bot", id: botId }],
        lastMessageAt: now(), lastMessagePreview: hello, unread: 0,
      },
      ...st.threads,
    ],
    messages: [...st.messages, { id: id(), threadId, author: { type: "bot", id: botId }, createdAt: now(), parts: [{ type: "text", text: hello }] }],
  }));
  return threadId;
}

/* ---------- Mock timers ---------- */
// Fake bot replies arrive on timers. They're tracked so reset() can cancel them;
// otherwise a reply started before a reset would appear in the fresh data.

const mockTimers = new Set<ReturnType<typeof setTimeout>>();

function later(run: () => void, ms: number) {
  const timer = setTimeout(() => {
    mockTimers.delete(timer);
    run();
  }, ms);
  mockTimers.add(timer);
}

function every(run: (stop: () => void) => void, ms: number) {
  const timer = setInterval(() => run(stop), ms);
  const stop = () => {
    clearInterval(timer);
    mockTimers.delete(timer);
  };
  mockTimers.add(timer);
}

function cancelMockTimers() {
  // clearTimeout and clearInterval cancel either kind of timer.
  mockTimers.forEach((timer) => clearTimeout(timer));
  mockTimers.clear();
}

function pushBotMessage(threadId: string, botId: string, parts: Message["parts"], status?: Message["status"]) {
  const msg: Message = { id: id(), threadId, author: { type: "bot", id: botId }, parts, createdAt: now(), status };
  set((st) => ({
    ...st,
    messages: [...st.messages, msg],
    threads: st.threads.map((t) =>
      t.id === threadId
        ? { ...t, lastMessageAt: msg.createdAt, lastMessagePreview: parts.find((p) => p.type === "text")?.text ?? t.lastMessagePreview }
        : t,
    ),
  }));
  return msg.id;
}

/** MOCK ONLY: simulates a bot streaming a reply. Real replies arrive over realtime. */
function fakeBotReply(threadId: string, botId: string, userText: string) {
  const bot = state.bots.find((b) => b.id === botId);
  if (!bot) return;
  set((st) => ({ ...st, bots: st.bots.map((b) => (b.id === botId ? { ...b, status: "working", statusText: "Thinking…" } : b)) }));

  const full = `Got it. I'll take care of “${userText.slice(0, 60)}${userText.length > 60 ? "…" : ""}” and report back here. (This is mock data; real bots arrive with the API.)`;
  const words = full.split(" ");
  let i = 0;
  let msgId: string | null = null;

  later(() => {
    msgId = pushBotMessage(
      threadId,
      botId,
      [{ type: "reasoning", text: `Reading the request, checking ${bot.name}'s tools and memory, planning steps.`, durationSec: 2 }, { type: "text", text: "" }],
      "streaming",
    );
    every((stop) => {
      i += 2;
      const text = words.slice(0, i).join(" ");
      const done = i >= words.length;
      set((st) => ({
        ...st,
        messages: st.messages.map((m) =>
          m.id === msgId
            ? { ...m, status: done ? "complete" : "streaming", parts: m.parts.map((p) => (p.type === "text" ? { ...p, text } : p)) }
            : m,
        ),
      }));
      if (done) {
        stop();
        set((st) => ({ ...st, bots: st.bots.map((b) => (b.id === botId ? { ...b, status: "idle", statusText: "Just replied" } : b)) }));
      }
    }, 60);
  }, 600);
}

/* ---------- Selectors ---------- */

export const selectBot = (botId?: string) => (s: State) => s.bots.find((b) => b.id === botId);
export const selectThread = (threadId?: string) => (s: State) => s.threads.find((t) => t.id === threadId);
export const selectPendingApprovals = (s: State) => s.approvals.filter((a) => a.status === "pending");

/* ---------- Named hooks: what screens actually use ---------- */
// Each hook reads one clear slice of data. Screens never write selectors themselves.

const newestFirst = (a: Thread, b: Thread) => b.lastMessageAt.localeCompare(a.lastMessageAt);

export const useOrg = () => useStore(useCallback((s: State) => s.org, []));
export const useOrgs = () => useStore(useCallback((s: State) => s.orgs, []));
export const useAuthStatus = () => useStore(useCallback((s: State) => s.authStatus, []));
export const useIsGuest = () => useStore(useCallback((s: State) => s.guest, []));
export const useCurrentUser = () => useStore(useCallback((s: State) => s.users.find((u) => u.id === s.currentUserId)!, []));
export const useUser = (id?: string) => useStore(useCallback((s: State) => s.users.find((u) => u.id === id), [id]));
export const useBot = (id?: string) => useStore(useCallback((s: State) => s.bots.find((b) => b.id === id), [id]));
export const useModel = (id?: string) => useStore(useCallback((s: State) => s.models.find((m) => m.id === id), [id]));
export const useThread = (id?: string) => useStore(useCallback((s: State) => s.threads.find((t) => t.id === id), [id]));

/** All threads, newest activity first. */
export const useThreads = () => useStore(useCallback((s: State) => [...s.threads].sort(newestFirst), []));

/** The thread with the most recent activity: where "/" takes you on bigger screens. */
export const useLatestThreadId = () => useStore(useCallback((s: State) => [...s.threads].sort(newestFirst)[0]?.id, []));

export const useThreadMessages = (threadId: string) =>
  useStore(useCallback((s: State) => s.messages.filter((m) => m.threadId === threadId), [threadId]));

export const useApproval = (id: string) => useStore(useCallback((s: State) => s.approvals.find((a) => a.id === id), [id]));
export const usePendingApprovalCount = () => useStore(useCallback((s: State) => selectPendingApprovals(s).length, []));

export const useBotRoutines = (botId?: string) =>
  useStore(useCallback((s: State) => s.routines.filter((r) => r.botId === botId), [botId]));

/** Memories this bot can use: its own plus the ones shared with every bot. */
export const useBotMemories = (botId?: string) =>
  useStore(useCallback((s: State) => s.memories.filter((m) => !m.botId || m.botId === botId), [botId]));

/* Whole-collection hooks for the app pages (marketplace, settings, approvals…). */
export const useBots = () => useStore(useCallback((s: State) => s.bots, []));
export const useBotsLoading = () => useStore(useCallback((s: State) => s.botsLoading, []));
export const useUsers = () => useStore(useCallback((s: State) => s.users, []));
export const useInvitations = () => useStore(useCallback((s: State) => s.invitations, []));
export const useModels = () => useStore(useCallback((s: State) => s.models, []));
export const useCredentials = () => useStore(useCallback((s: State) => s.credentials, []));
export const useTemplates = () => useStore(useCallback((s: State) => s.templates, []));
export const useRoutines = () => useStore(useCallback((s: State) => s.routines, []));
export const useMemories = () => useStore(useCallback((s: State) => s.memories, []));
export const useUsage = () => useStore(useCallback((s: State) => s.usage, []));
export const useConnectors = () => useStore(useCallback((s: State) => s.connectors, []));
export const useConnections = () => useStore(useCallback((s: State) => s.connections, []));

/** Every approval, waiting ones first, then newest first. */
export const useApprovals = () =>
  useStore(
    useCallback(
      (s: State) =>
        [...s.approvals].sort(
          (a, b) => Number(b.status === "pending") - Number(a.status === "pending") || b.requestedAt.localeCompare(a.requestedAt),
        ),
      [],
    ),
  );

/** Display name for whoever wrote a message or is in a thread. */
export const useParticipantName = (p?: Participant | { type: "system"; id: "system" }) =>
  useStore(
    useCallback(
      (s: State) => {
        if (!p || p.type === "system") return "BotDesk";
        if (p.type === "bot") return s.bots.find((b) => b.id === p.id)?.name ?? "Unknown bot";
        return s.users.find((u) => u.id === p.id)?.name ?? "Unknown member";
      },
      [p],
    ),
  );
