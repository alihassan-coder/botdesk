"use client";

/**
 * Client-side data store for the UI.
 *
 * Two modes, picked by NEXT_PUBLIC_API_URL:
 * - Set: apps/api (see `./api`) holds accounts (sign-in, profile, password), your
 *   organizations, their members, invitations and bots, and your chats: the chat list,
 *   each bot's DM, message history, sending, and bot replies streamed live over the
 *   chat's event stream (with a Stop button), and approvals: cards in the chat, live from
 *   the stream, and the Approvals page from the list; and Models & keys: providers, their
 *   keys and live model lists; what each bot remembers (Memory), loaded per bot; and Usage &
 *   budgets: daily spend, each bot's spend this month and the org's budget. Routines and
 *   apps aren't on the API yet, so they start empty or stay mock.
 * - Not set (tests, e2e, demos): everything is the in-memory mock, with fake bot replies.
 * Guest mode ("Explore the demo") uses the mock in either case, so people can look
 * around without an account; it never calls the API.
 * Screens can't tell the difference: they use the hooks and actions below either way.
 */
import { useCallback, useRef, useSyncExternalStore } from "react";
import { makeHandle } from "@/lib/handle";
import { parseMentions } from "@/lib/mentions";
import { previewFromArgs } from "@/lib/args-form";
import { approvalApi, authApi, botApi, inviteApi, memoryApi, modelApi, orgApi, runApi, threadApi, usageApi } from "./api/botdesk";
import { ApiError, apiBaseUrl } from "./api/client";
import { toApiBot, toApproval, toBot, toInvitation, toMemory, toMemoryStatus, toMessage, toModel, toModelProvider, toOrg, toThread, toUsage, toUser } from "./api/map";
import { applyRunEvent, typingId, upsertApproval, withActiveRuns, withPreview, withWaitingApprovals, type ActiveRun } from "./api/run-events";
import type { ApiMe, ApiRunEvent, ApiThread, ApiThreadRuns } from "./api/types";
import * as mock from "./mock/fixtures";
import type {
  Approval, ApprovalStatus, Bot, Invitation, MemoryItem, MemoryList, MemoryStatus, Membership, Message, Model, ModelListProblem, ModelProvider, Org,
  Participant, Routine, Thread, UsageSummary, User,
} from "./types";

/** What you fill in to create a bot; the rest (id, handle, status…) is filled in for you. */
export type NewBotInput = Pick<
  Bot,
  "name" | "role" | "description" | "avatarColor" | "modelId" | "securityLevel" | "computerMode" | "instructions" | "monthlyBudgetUsd"
> & Partial<Pick<Bot, "memoryEnabled">>;

/** What you pick to start a group chat. You're in it anyway, so leave yourself out of `userIds`. */
export interface NewGroupInput {
  title: string;
  botIds: string[];
  userIds: string[];
}

/** What you fill in to create a routine. */
export type NewRoutineInput = Pick<Routine, "botId" | "name" | "description" | "schedule" | "steps" | "enabled">;

/** "unknown" until the browser has checked for a saved session (first render, server). */
export type AuthStatus = "unknown" | "signed-in" | "signed-out";

/** Whether a chat's messages have arrived from the API, and whether there are older ones to load. */
export interface ThreadLoad {
  status: "loading" | "ready" | "error";
  hasOlder: boolean;
}

/** What an action that can fail returns: screens show `error` as is. */
export type ActionResult = { ok: true } | { ok: false; error: string };

/**
 * Deciding an approval: `conflict` when someone decided first or it expired (the card now shows
 * what happened, and `status` says what that was), `invalid` when the edited fields don't fit
 * the action (`error` says which). Any other failure leaves it waiting, so an edit can be kept.
 */
export type DecideResult =
  | { ok: true }
  | { ok: false; error: string; reason?: "conflict" | "invalid"; status?: ApprovalStatus };

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
  /** True while the current org's bots and chats are on their way from the API. */
  botsLoading: boolean;
  threads: Thread[];
  messages: Message[];
  /** API only: which chats' messages have been loaded. The mock has them all from the start. */
  threadLoads: Record<string, ThreadLoad>;
  /** API only: bot replies in progress. The mock fakes its replies without these. */
  runs: ActiveRun[];
  /** API only: runs seen finish, so a late event can't revive one (see api/run-events.ts). */
  endedRunIds: string[];
  approvals: Approval[];
  connectors: typeof mock.connectors;
  connections: typeof mock.connections;
  routines: typeof mock.routines;
  /** Models & keys: the live model list of every connected provider, and the providers themselves. */
  models: Model[];
  modelProviders: ModelProvider[];
  /** Connected providers whose model list couldn't be fetched last time. */
  modelProblems: ModelListProblem[];
  /** API only: true while providers and models are on their way. */
  modelsLoading: boolean;
  /** MOCK: every memory of every bot. On the API, memories are loaded per bot into `memoryLists`. */
  memories: MemoryItem[];
  /** Each bot's memories as last loaded (or searched), by bot id. */
  memoryLists: Record<string, MemoryList>;
  /** Whether bots can remember here. Null until the API has said. */
  memoryStatus: MemoryStatus | null;
  /** Settings → Usage & budgets. Each bot's own spend is on the bot. */
  usage: UsageSummary;
  /** API only: true while the usage report is on its way. */
  usageLoading: boolean;
  /** API only: each bot's spend this month, by bot id, so bots loaded after the report still show it. */
  spentByBot: Record<string, number>;
  templates: typeof mock.templates;
}

/** No usage yet (API mode, before the report arrives). Defined here: the seeds below run at import. */
const EMPTY_USAGE: UsageSummary = { days: [], monthToDateUsd: 0, unpricedTokens: 0 };

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
    threadLoads: {},
    runs: [],
    endedRunIds: [],
    approvals: mock.approvals,
    connectors: mock.connectors,
    connections: mock.connections,
    routines: mock.routines,
    models: mock.models,
    modelProviders: mock.modelProviders,
    modelProblems: [],
    modelsLoading: false,
    memories: mock.memories,
    memoryLists: {},
    memoryStatus: { enabled: true },
    usage: mockUsage(),
    usageLoading: false,
    spentByBot: {},
    templates: mock.templates,
  };
}

/**
 * Before the API answers, in API mode: nothing yet, and no demo data either. The org and
 * user are blank stand-ins (screens behind the auth gate still prerender and read them).
 */
function apiSeed(): State {
  const blankUser: User = { id: "", name: "", email: "", handle: "", role: "member", presence: "online" };
  return {
    ...seed(),
    org: { id: "", name: "", slug: "", plan: "self-hosted" },
    orgs: [],
    users: [blankUser],
    currentUserId: "",
    passwords: {},
    bots: [],
    botsLoading: true,
    threads: [],
    messages: [],
    approvals: [],
    routines: [],
    memories: [],
    memoryStatus: null,
    models: [],
    modelProviders: [],
    usage: EMPTY_USAGE,
    usageLoading: true,
  };
}

/** Where the store starts, and where signing out of the demo goes back to. */
const initialState = (): State => (apiBaseUrl() ? apiSeed() : seed());

let state: State = initialState();
/**
 * What the server rendered with, which is also what the browser must hydrate with, however far
 * the browser's own state has moved on by then (a Suspense boundary can hydrate after the
 * session is restored). In API mode it has no demo data, so the chat list shows its skeleton.
 */
const serverState = state;
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
const getServerSnapshot = () => serverState;

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
  closeChatStreams();
  set((st) => ({
    ...st,
    org: toOrg(org),
    users: st.users.filter((u) => u.id === st.currentUserId).map((u) => ({ ...u, role: org.role })),
    invitations: [],
    bots: [],
    threads: [],
    // The demo's chats, approvals, routines and memories belong to the demo bots, not to this org.
    messages: [],
    threadLoads: {},
    runs: [],
    endedRunIds: [],
    approvals: [],
    models: [],
    modelProviders: [],
    modelProblems: [],
    modelsLoading: true,
    routines: [],
    memories: [],
    memoryLists: {},
    memoryStatus: null,
    botsLoading: true,
    usage: EMPTY_USAGE,
    usageLoading: true,
    spentByBot: {},
  }));
  void loadOrgPeople(org);
  void loadBotsAndChats(org);
  void loadModelCatalog(org.id);
  void loadUsage(org.id);
}

/**
 * The org's bots and your chats. Every bot has a DM in the sidebar, so a bot you haven't
 * talked to yet (say, a teammate just hired it) gets its DM opened here, once.
 */
async function loadBotsAndChats(org: Membership) {
  const [apiBots, apiThreads] = await Promise.all([
    botApi.list(org.id).catch(() => null),
    threadApi.list(org.id).catch(() => null),
  ]);
  const bots = withSpend(apiBots?.map(toBot) ?? [], state.spentByBot);
  const threads = apiThreads ?? [];
  const withoutDm = bots.filter((b) => !threads.some((t) => t.kind === "dm" && t.botId === b.id));
  const opened = await Promise.all(withoutDm.map((b) => threadApi.openDm(org.id, b.id).catch(() => null)));

  set((st) => {
    if (st.org.id !== org.id) return st; // switched org while loading
    const all = [...threads, ...opened.filter((t): t is ApiThread => t !== null)];
    const spent = withSpend(bots, st.spentByBot); // the usage report may have come in meanwhile
    return { ...st, bots: spent, threads: all.map((t) => withBotName(toThread(t), spent)), botsLoading: false };
  });
}

/*
 * A DM is named after its bot. The API names it once, when the chat starts, and keeps
 * that title when the bot is renamed, so the bot's current name is used instead.
 */
function withBotName(thread: Thread, bots: Bot[]): Thread {
  const bot = thread.kind === "dm" ? bots.find((b) => b.id === thread.botId) : undefined;
  return bot ? { ...thread, title: bot.name } : thread;
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
  set(() => initialState());
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
    closeChatStreams();
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

  /** Set a new password from an emailed reset link. The API signs out every device, this one too. */
  async resetPassword(token: string, password: string): Promise<ActionResult> {
    if (isDemoMode()) return { ok: true }; // MOCK: there are no reset links without the API.
    try {
      await authApi.resetPassword(token, password);
      set((st) => ({ ...st, authStatus: "signed-out" }));
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

/* ---------- Chats on the API ----------
 * Opening a chat loads its newest messages and follows its event stream, where your
 * messages and the bots' replies arrive (see api/run-events.ts). Closing it stops following.
 */
const PAGE_SIZE = 50;

/** Close functions for the event streams of the chats that are open, by thread id. */
const chatStreams = new Map<string, () => void>();

function closeChatStreams() {
  chatStreams.forEach((close) => close());
  chatStreams.clear();
}

function followChat(orgId: string, threadId: string, after?: number): () => void {
  chatStreams.get(threadId)?.();
  const close = threadApi.follow(orgId, threadId, (event) => onRunEvent(orgId, event), after);
  chatStreams.set(threadId, close);
  return () => {
    close();
    if (chatStreams.get(threadId) === close) chatStreams.delete(threadId);
  };
}

function onRunEvent(orgId: string, event: ApiRunEvent) {
  set((st) => (st.org.id === orgId ? withRunStatus({ ...st, ...applyRunEvent(st, event) }) : st));
  if (event.kind === "run_finished" || event.kind === "run_failed") scheduleUsageRefresh(orgId);
  // Someone asked or decided: the sidebar count may be behind on other chats too.
  if (event.kind === "approval_requested" || event.kind === "approval_decided") void approvalActions.refreshPendingApprovals();
}

/** NEEDS_ATTENTION marks the "error" status this file set, so it can be cleared again. */
const NEEDS_ATTENTION = "Needs attention";

/**
 * A bot's status follows its run: working while it replies, waiting while a decision is
 * pending, needs attention when a person must check; back to idle when it's done.
 */
function withRunStatus(st: State): State {
  let changed = false;
  const bots = st.bots.map((bot) => {
    const runs = st.runs.filter((r) => r.botId === bot.id);
    const next = runStatus(runs);
    if (next && (bot.status !== next.status || bot.statusText !== next.statusText)) {
      changed = true;
      return { ...bot, ...next };
    }
    const setByRuns = bot.status === "working" || bot.status === "waiting-approval" || bot.statusText === NEEDS_ATTENTION;
    if (!next && setByRuns) {
      changed = true;
      return { ...bot, status: "idle" as const, statusText: undefined };
    }
    return bot;
  });
  return changed ? { ...st, bots } : st;
}

/** The most urgent of a bot's runs decides how it shows. */
function runStatus(runs: ActiveRun[]): Pick<Bot, "status" | "statusText"> | undefined {
  if (runs.some((r) => r.status === "needs_attention")) return { status: "error", statusText: NEEDS_ATTENTION };
  if (runs.some((r) => r.status === "waiting_approval")) return { status: "waiting-approval", statusText: "Waiting for approval" };
  const running = runs[0];
  if (!running) return undefined;
  return { status: "working", statusText: running.messageId ? "Replying…" : "Thinking…" };
}

const setThreadLoad = (threadId: string, load: ThreadLoad) =>
  set((st) => ({ ...st, threadLoads: { ...st.threadLoads, [threadId]: load } }));

/**
 * The newest page of messages, and the chat's approvals so their cards can show (a reply still
 * being written gets a stand-in, see withWaitingApprovals). `active` (null if that list failed)
 * sets this chat's runs. Messages that arrived on the stream meanwhile are kept.
 */
async function loadMessages(orgId: string, threadId: string, active: ApiThreadRuns | null = null) {
  const activeRuns = active?.runs ?? null;
  setThreadLoad(threadId, { status: "loading", hasOlder: state.threadLoads[threadId]?.hasOlder ?? false });
  try {
    const [apiPage, apiApprovals] = await Promise.all([
      threadApi.messages(orgId, threadId, { limit: PAGE_SIZE }),
      approvalApi.list(orgId, { status: "all", threadId }).catch(() => []),
    ]);
    const page = apiPage.map(toMessage);
    set((st) => {
      if (st.org.id !== orgId) return st;
      const others = st.messages.filter((m) => m.threadId !== threadId);
      const kept = st.messages.filter((m) => m.threadId === threadId && keepBesidePage(st, m, page));
      const loaded = {
        ...st,
        messages: [...others, ...page, ...kept],
        threadLoads: { ...st.threadLoads, [threadId]: { status: "ready" as const, hasOlder: page.length === PAGE_SIZE } },
      };
      const withCards = withWaitingApprovals(loaded, apiApprovals.map(toApproval), activeRuns ?? undefined);
      return withRunStatus({ ...loaded, ...(active ? withActiveRuns(withCards, threadId, active.runs, active.lastEventId) : withCards) });
    });
  } catch {
    if (state.org.id === orgId) setThreadLoad(threadId, { status: "error", hasOlder: false });
  }
}

/**
 * A message of this chat already in the store that the newly loaded page doesn't have. Kept: the
 * reply of a run still going (its stand-in, or its streamed words), whatever its time, and
 * anything saved since the page's oldest message (it arrived on the stream after the page was
 * read). Dropped: older ones from an earlier visit, which would leave a gap before the page.
 */
function keepBesidePage(st: State, message: Message, page: Message[]): boolean {
  if (page.some((m) => m.id === message.id)) return false;
  if (st.runs.some((r) => message.id === typingId(r.id) || message.id === r.messageId)) return true;
  const oldest = page[0]?.createdAt;
  return oldest === undefined || Date.parse(message.createdAt) >= Date.parse(oldest);
}

const chatActions = {
  /**
   * Call when a chat opens; call what it returns when it closes. On the API this loads the
   * chat's messages and follows its live updates. The mock has everything already.
   */
  openThread(threadId: string): () => void {
    if (isDemoMode() || !state.threads.some((t) => t.id === threadId)) return () => {};
    const orgId = state.org.id;
    setThreadLoad(threadId, { status: "loading", hasOlder: state.threadLoads[threadId]?.hasOlder ?? false });
    let closed = false;
    let stopFollowing = () => {};
    void (async () => {
      // The chat's runs first. The stream starts at their `replayFrom`, just before the running
      // runs' first events, so it replays a reply's words and tool lines so far; the messages are
      // read after that, so nothing that happens in between is missed. If the list fails, the
      // stream starts from now, as a best effort.
      const active = await threadApi.activeRuns(orgId, threadId).catch(() => null);
      if (closed || state.org.id !== orgId) return;
      stopFollowing = followChat(orgId, threadId, active?.replayFrom);
      await loadMessages(orgId, threadId, active);
    })();
    return () => {
      closed = true;
      stopFollowing();
    };
  },

  /** The page of messages before the oldest one shown. API only. */
  async loadOlderMessages(threadId: string): Promise<ActionResult> {
    const oldest = state.messages.find((m) => m.threadId === threadId);
    if (isDemoMode() || !oldest) return { ok: true };
    const orgId = state.org.id;
    try {
      const page = (await threadApi.messages(orgId, threadId, { limit: PAGE_SIZE, before: oldest.createdAt })).map(toMessage);
      set((st) => {
        if (st.org.id !== orgId) return st;
        const known = new Set(st.messages.map((m) => m.id));
        const older = page.filter((m) => !known.has(m.id));
        const at = st.messages.findIndex((m) => m.threadId === threadId);
        const messages = at === -1 ? [...st.messages, ...older] : [...st.messages.slice(0, at), ...older, ...st.messages.slice(at)];
        return { ...st, messages, threadLoads: { ...st.threadLoads, [threadId]: { status: "ready", hasOlder: page.length === PAGE_SIZE } } };
      });
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Stop the bot replies in progress in this chat. API only: mock replies finish on their own. */
  async stopReplies(threadId: string): Promise<ActionResult> {
    const runs = state.runs.filter((r) => r.threadId === threadId);
    const orgId = state.org.id;
    try {
      await Promise.all(runs.map((r) => runApi.cancel(orgId, r.id)));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Stop one run, say one that needs attention. Its waiting approvals expire. API only. */
  async stopRun(runId: string): Promise<ActionResult> {
    if (isDemoMode()) return { ok: true };
    try {
      await runApi.cancel(state.org.id, runId);
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /**
   * Starts a group chat with you plus the bots and people you pick, and returns its id so
   * the screen can open it. A group needs at least one bot: they're who does the work.
   */
  async createGroup(input: NewGroupInput): Promise<ActionResult & { threadId?: string }> {
    const title = input.title.trim();
    if (!title) return { ok: false, error: "Give the group a name." };
    if (input.botIds.length === 0) return { ok: false, error: "Pick at least one bot." };
    const userIds = input.userIds.filter((u) => u !== state.currentUserId);

    let thread: Thread;
    if (isDemoMode()) {
      thread = {
        id: `t_${id()}`, kind: "group", title,
        participants: [
          { type: "user", id: state.currentUserId },
          ...userIds.map((u) => ({ type: "user" as const, id: u })),
          ...input.botIds.map((b) => ({ type: "bot" as const, id: b })),
        ],
        lastMessageAt: now(), lastMessagePreview: "", unread: 0,
      };
    } else {
      try {
        thread = toThread(await threadApi.createGroup(state.org.id, { title, botIds: input.botIds, userIds }));
      } catch (error) {
        return failure(error);
      }
    }
    set((st) => ({ ...st, threads: [thread, ...st.threads.filter((t) => t.id !== thread.id)] }));
    return { ok: true, threadId: thread.id };
  },
};

/**
 * Shows your message at once, then sends it. The API answers with the saved message and the
 * runs it started; the replies themselves arrive on the chat's event stream.
 */
async function sendApiMessage(threadId: string, text: string, mentions: Participant[]) {
  const orgId = state.org.id;
  const local: Message = {
    id: `local-${id()}`, threadId, author: { type: "user", id: state.currentUserId },
    parts: [{ type: "text", text }], createdAt: now(), mentions,
  };
  set((st) => ({ ...st, messages: [...st.messages, local], threads: withPreview(st.threads, local) }));

  try {
    const sent = await threadApi.send(orgId, threadId, text);
    const saved = { ...toMessage(sent), mentions };
    set((st) => {
      if (st.org.id !== orgId) return st;
      // The stream may have delivered the saved message first; then just drop the local copy.
      const arrived = st.messages.some((m) => m.id === saved.id);
      const messages = arrived ? st.messages.filter((m) => m.id !== local.id) : st.messages.map((m) => (m.id === local.id ? saved : m));
      const newRuns = sent.runIds.filter((runId) => !st.runs.some((r) => r.id === runId)).map((runId) => ({ id: runId, threadId }));
      return { ...st, messages, runs: [...st.runs, ...newRuns] };
    });
  } catch (error) {
    const reason = failure(error).error;
    set((st) => ({
      ...st,
      messages: st.messages.map((m) => (m.id === local.id ? { ...m, status: "error" as const, error: `Not sent. ${reason}` } : m)),
    }));
  }
}

/* ---------- Approvals ----------
 * On the API, cards in a chat come from its event stream; the Approvals page and the sidebar
 * count come from the list, which the shell polls (there's no org-wide stream yet).
 * In the mock, deciding updates the card and the bot confirms in its chat.
 */
const approvalActions = {
  /**
   * Approve or deny. Approving with `editedArgs` runs the action with your changes ("edited").
   * If someone else decided first (409), the card is refreshed to show what happened.
   */
  async decideApproval(approvalId: string, decision: "approve" | "deny", editedArgs?: Record<string, unknown>): Promise<DecideResult> {
    if (isDemoMode()) {
      decideMockApproval(approvalId, decision, editedArgs);
      return { ok: true };
    }
    const orgId = state.org.id;
    try {
      const decided = await approvalApi.decide(orgId, approvalId, { decision, ...(editedArgs ? { editedArgs } : {}) });
      putApprovals(orgId, [toApproval(decided)]);
      return { ok: true };
    } catch (error) {
      const { error: message } = failure(error);
      const status = error instanceof ApiError ? error.status : 0;
      // A 409 is also "this tool isn't available any more", while the approval still waits:
      // only a decision we can see counts as a conflict.
      const latest = status === 409 || status === 404 ? await approvalApi.get(orgId, approvalId).catch(() => null) : null;
      if (latest) putApprovals(orgId, [toApproval(latest)]);
      const decided = latest !== null && latest.status !== "pending";
      const reason = status === 400 ? "invalid" : decided ? "conflict" : undefined;
      return { ok: false, error: message, ...(reason ? { reason } : {}), ...(latest ? { status: latest.status } : {}) };
    }
  },

  /** Every approval in your chats (the newest 100), for the Approvals page. API only. */
  async loadApprovals(): Promise<ActionResult> {
    if (isDemoMode()) return { ok: true };
    const orgId = state.org.id;
    try {
      putApprovals(orgId, (await approvalApi.list(orgId, { status: "all" })).map(toApproval));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /**
   * What's waiting now, for the sidebar count. One we thought was waiting but isn't in the list
   * any more was decided somewhere we weren't watching, so it's fetched again. API only.
   */
  async refreshPendingApprovals(): Promise<void> {
    if (isDemoMode() || state.authStatus !== "signed-in") return;
    const orgId = state.org.id;
    const pending = await approvalApi.list(orgId, { status: "pending" }).catch(() => null);
    if (!pending) return;
    const stillPending = new Set(pending.map((a) => a.id));
    const settled = state.approvals.filter((a) => a.status === "pending" && !stillPending.has(a.id));
    const refetched = await Promise.all(settled.map((a) => approvalApi.get(orgId, a.id).catch(() => null)));
    putApprovals(orgId, [...pending, ...refetched.filter((a) => a !== null)].map(toApproval));
  },
};

/** Adds or updates approvals, unless you switched org meanwhile. */
function putApprovals(orgId: string, approvals: Approval[]) {
  set((st) => (st.org.id === orgId ? { ...st, approvals: approvals.reduce(upsertApproval, st.approvals) } : st));
}

/** MOCK: decide at once; the bot's status follows, and it confirms in the chat. */
function decideMockApproval(approvalId: string, decision: "approve" | "deny", editedArgs?: Record<string, unknown>) {
  const before = state.approvals.find((a) => a.id === approvalId);
  if (!before || before.status !== "pending") return;
  const edited = decision === "approve" && editedArgs !== undefined && JSON.stringify(editedArgs) !== JSON.stringify(before.args);
  const status: ApprovalStatus = decision === "deny" ? "denied" : edited ? "edited" : "approved";
  const decidedAt = now();
  set((st) => ({
    ...st,
    approvals: st.approvals.map((a) =>
      a.id === approvalId
        ? {
            ...a, status, decidedBy: st.currentUserId, decidedAt,
            ...(decision === "approve" ? { finalArgs: editedArgs ?? a.args ?? null } : {}),
            ...(edited ? { preview: previewFromArgs(editedArgs) } : {}),
          }
        : a,
    ),
  }));

  // Keep the bot's status honest: how many decisions does it still need from you?
  const stillWaiting = state.approvals.filter((x) => x.botId === before.botId && x.status === "pending").length;
  actions.updateBot(
    before.botId,
    stillWaiting > 0
      ? { status: "waiting-approval", statusText: `${stillWaiting} waiting for you` }
      : { status: "idle", statusText: "All caught up" },
  );

  // MOCK: the bot confirms. Real bots report the actual result of the action.
  const text = decision === "approve" ? `Done: ${before.title}.` : `Okay, I won't go ahead with “${before.title}”.`;
  later(() => pushBotMessage(before.threadId, before.botId, [{ type: "text", text }]), 700);
}

/* ---------- Models & keys ----------
 * Model providers, their keys, and the live list of models bots can pick from
 * (Settings → Models & keys, the bot model picker). On the API a key goes in and never
 * comes back: the store only ever holds its last 4 characters. In the demo a key "works"
 * unless it starts with "bad", so the error path can be tried too.
 */

/**
 * What you type to connect a provider. Custom servers add a name and a base URL; their key may be
 * empty. Editing one, an empty key keeps the saved key unless the base URL changes; `noKey` drops it.
 */
export interface ProviderKeyInput {
  apiKey: string;
  baseUrl?: string;
  label?: string;
  noKey?: boolean;
}

/** The org's providers and every connected provider's models, fetched together. */
async function loadModelCatalog(orgId: string, refresh = false) {
  set((st) => ({ ...st, modelsLoading: true }));
  const [providers, list] = await Promise.all([
    modelApi.providers(orgId).catch(() => null),
    modelApi.models(orgId, refresh).catch(() => null),
  ]);
  set((st) => {
    if (st.org.id !== orgId) return st; // switched org while loading
    return {
      ...st,
      modelProviders: providers?.map(toModelProvider) ?? st.modelProviders,
      models: list?.models.map(toModel) ?? st.models,
      modelProblems: list ? list.errors : [{ provider: "", message: "Couldn't load the models. Try again in a moment." }],
      modelsLoading: false,
    };
  });
}

function withProvider(providers: ModelProvider[], saved: ModelProvider) {
  return providers.some((p) => p.id === saved.id) ? providers.map((p) => (p.id === saved.id ? saved : p)) : [...providers, saved];
}

const keyHintOf = (key: string) => (key.length >= 12 ? key.slice(-4) : undefined);
const CUSTOM_HINT = "Any OpenAI-compatible server: Ollama, LM Studio, vLLM.";
/** MOCK: what a newly connected provider offers in the demo. */
const MOCK_NEW_MODELS: Record<string, Model[]> = {
  groq: [{ id: "groq:llama-3.3-70b-versatile", provider: "groq", name: "llama-3.3-70b-versatile", contextWindow: 131_072 }],
};

/** MOCK: "checks" the key, then connects the provider (or adds a custom server). */
function saveMockKey(providerId: string, { apiKey, baseUrl, label, noKey }: ProviderKeyInput): ActionResult {
  const key = apiKey.trim();
  if (key.startsWith("bad")) return { ok: false, error: "That key didn't work: 401: Incorrect API key provided." };
  const existing = state.modelProviders.find((p) => p.id === providerId);
  const isNewCustom = providerId === "custom";
  if (!existing && !isNewCustom) return { ok: false, error: "We don't support that provider." };
  const kind = existing?.kind ?? "custom";
  if (kind !== "custom" && !key) return { ok: false, error: "Paste the API key." };
  const newUrl = baseUrl?.trim().replace(/\/+$/, "") || existing?.baseUrl;
  const keepsKey = kind === "custom" && !key && !noKey && existing?.keyHint !== undefined;
  if (keepsKey && newUrl !== existing?.baseUrl) {
    return { ok: false, error: "You changed the base URL, so paste the API key again (or choose No key). A saved key is never sent to a new address." };
  }
  const hint = keepsKey ? existing?.keyHint : keyHintOf(key);
  const saved: ModelProvider = {
    id: isNewCustom ? `custom-${id()}` : providerId,
    kind,
    name: label?.trim() || existing?.name || "Custom",
    hint: existing?.hint ?? CUSTOM_HINT,
    connected: true, source: "org", status: "ok", lastVerifiedAt: now(),
    ...(hint ? { keyHint: hint } : {}),
    ...(kind === "custom" ? { baseUrl: newUrl } : {}),
  };
  const added = (MOCK_NEW_MODELS[saved.id] ?? []).filter((m) => !state.models.some((known) => known.id === m.id));
  set((st) => ({ ...st, modelProviders: withProvider(st.modelProviders, saved), models: [...st.models, ...added] }));
  return { ok: true };
}

/** A built-in provider goes back to "Add key"; a custom server goes away. Its models go with it. */
function forgetProviderKey(providerId: string) {
  set((st) => ({
    ...st,
    modelProviders: st.modelProviders.flatMap((p) => {
      if (p.id !== providerId) return [p];
      return p.kind === "custom" ? [] : [{ id: p.id, kind: p.kind, name: p.name, hint: p.hint, connected: false }];
    }),
    models: st.models.filter((m) => m.provider !== providerId),
  }));
}

const modelActions = {
  /** Fetch providers and models again. `refresh` skips the API's ~10 minute cache. */
  loadModels({ refresh = false }: { refresh?: boolean } = {}): Promise<void> {
    if (isDemoMode()) return Promise.resolve();
    return loadModelCatalog(state.org.id, refresh);
  },

  /** Add or replace a provider's key (owners and admins). The API checks it live first. "custom" adds a server. */
  async saveProviderKey(providerId: string, input: ProviderKeyInput): Promise<ActionResult> {
    if (isDemoMode()) return saveMockKey(providerId, input);
    const orgId = state.org.id;
    try {
      const saved = toModelProvider(await modelApi.saveKey(orgId, providerId, input));
      set((st) => (st.org.id === orgId ? { ...st, modelProviders: withProvider(st.modelProviders, saved) } : st));
    } catch (error) {
      return failure(error);
    }
    void loadModelCatalog(orgId);
    return { ok: true };
  },

  /** Check a saved key again. `ok: false` carries the provider's reason. */
  async testProviderKey(providerId: string): Promise<ActionResult> {
    if (isDemoMode()) {
      set((st) => ({ ...st, modelProviders: st.modelProviders.map((p) => (p.id === providerId ? { ...p, status: "ok", lastVerifiedAt: now() } : p)) }));
      return { ok: true };
    }
    try {
      const result = await modelApi.testKey(state.org.id, providerId);
      set((st) => ({ ...st, modelProviders: withProvider(st.modelProviders, toModelProvider(result.provider)) }));
      return result.ok ? { ok: true } : { ok: false, error: result.error ?? "That key didn't work." };
    } catch (error) {
      return failure(error);
    }
  },

  /** Remove the org's key. On the API, a key set on the server may still keep the provider connected. */
  async removeProviderKey(providerId: string): Promise<ActionResult> {
    if (isDemoMode()) {
      forgetProviderKey(providerId);
      return { ok: true };
    }
    try {
      await modelApi.removeKey(state.org.id, providerId);
    } catch (error) {
      return failure(error);
    }
    forgetProviderKey(providerId); // at once; the reload below says whether a server key takes over
    void loadModelCatalog(state.org.id);
    return { ok: true };
  },
};

/* ---------- Usage and budgets ----------
 * What the org's bots spent (Settings → Usage & budgets, a bot's "Budget this month") and the
 * org's monthly budget. On the API the report is loaded with the org, again when a usage screen
 * opens, and shortly after replies finish. A budget of 0 (bots) or none (the org) is no limit.
 */


/** MOCK: the demo's 14 days, and this month as the sum of what the demo bots spent. */
function mockUsage(): UsageSummary {
  return { days: mock.usage, monthToDateUsd: mock.bots.reduce((sum, b) => sum + b.spentThisMonthUsd, 0), unpricedTokens: 0 };
}

function withSpend(bots: Bot[], spentByBot: Record<string, number>): Bot[] {
  return bots.map((b) => (b.id in spentByBot && b.spentThisMonthUsd !== spentByBot[b.id] ? { ...b, spentThisMonthUsd: spentByBot[b.id] } : b));
}

async function loadUsage(orgId: string) {
  const report = await usageApi.org(orgId).catch(() => null);
  set((st) => {
    if (st.org.id !== orgId) return st; // switched org while loading
    if (!report) return { ...st, usageLoading: false };
    const { summary, spentByBot } = toUsage(report);
    return { ...st, usage: summary, usageLoading: false, spentByBot, bots: withSpend(st.bots, spentByBot) };
  });
}

/** Replies cost money: load the report again a moment after they finish, once for a burst of them. */
const USAGE_REFRESH_MS = 2_000;
let usageRefresh: ReturnType<typeof setTimeout> | undefined;

function scheduleUsageRefresh(orgId: string) {
  if (usageRefresh) return;
  usageRefresh = setTimeout(() => {
    usageRefresh = undefined;
    if (state.org.id === orgId && !isDemoMode()) void loadUsage(orgId);
  }, USAGE_REFRESH_MS);
}

const usageActions = {
  /** Fetch the usage report again (a usage screen opened). */
  loadUsage(): Promise<void> {
    if (isDemoMode()) return Promise.resolve();
    return loadUsage(state.org.id);
  },

  /** What all the org's bots may spend a month; null or 0 removes the limit. Owners and admins. */
  async setOrgBudget(usd: number | null): Promise<ActionResult> {
    const budget = usd ? Math.round(usd) : undefined;
    if (!isDemoMode()) {
      try {
        await orgApi.update(state.org.id, { monthlyBudgetUsd: budget ?? null });
      } catch (error) {
        return failure(error);
      }
    }
    set((st) => ({ ...st, usage: { ...st.usage, orgBudgetUsd: budget } }));
    return { ok: true };
  },
};

export const actions = {
  ...authActions,
  ...orgActions,
  ...chatActions,
  ...approvalActions,
  ...modelActions,
  ...usageActions,

  /** Sends your message. Bots reply in a moment: in a DM that bot, in a group the ones you @mention. */
  sendMessage(threadId: string, text: string) {
    const s = state;
    const mentions = parseMentions(text, s.bots, s.users);
    if (!isDemoMode()) return void sendApiMessage(threadId, text, mentions);

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

  /* ---------- Memory ----------
   * On the API, a bot's memories are loaded (or searched) one bot at a time into `memoryLists`.
   * MOCK: `memories` holds every bot's, and each change re-reads the open lists from it.
   */

  /** Whether bots can remember on this server, and if not, why. The demo always can. */
  async loadMemoryStatus() {
    if (isDemoMode()) return;
    const orgId = state.org.id;
    const status = await memoryApi.status(orgId).catch(() => null);
    set((st) => {
      if (st.org.id !== orgId) return st;
      return { ...st, memoryStatus: status ? toMemoryStatus(status) : { enabled: false, reason: "Couldn't check whether memory is on. Reload to try again." } };
    });
  },

  /** A bot's memories, newest first; with a query, the closest matches (on the API) or the ones that contain it (mock). */
  async loadMemories(botId: string, query = "") {
    if (isDemoMode()) return void setMemoryList(botId, { status: "ready", query, items: mockMemoriesOf(state.memories, botId, query) });
    const orgId = state.org.id;
    const request = (memoryRequests.get(botId) ?? 0) + 1;
    memoryRequests.set(botId, request);
    const current = () => memoryRequests.get(botId) === request && state.org.id === orgId; // a newer search wins
    setMemoryList(botId, { status: "loading", query, items: state.memoryLists[botId]?.items ?? [] });
    try {
      const items = (await memoryApi.list(orgId, botId, query)).map((m) => toMemory(m, botId));
      if (current()) setMemoryList(botId, { status: "ready", query, items });
    } catch (error) {
      if (current()) setMemoryList(botId, { status: "error", query, items: [], error: failure(error).error });
    }
  },

  /** Forget one memory. Members may forget only what the bot learned in their own DM. */
  async forgetMemory(botId: string, memoryId: string): Promise<ActionResult> {
    if (!isDemoMode()) {
      try {
        await memoryApi.forget(state.org.id, botId, memoryId);
      } catch (error) {
        return failure(error);
      }
    }
    set((st) => ({ ...st, memories: st.memories.filter((m) => m.id !== memoryId) }));
    updateMemoryList(botId, (items) => items.filter((m) => m.id !== memoryId));
    supersedeMemoryLoads(botId);
    return { ok: true };
  },

  /** Put right something a bot remembers wrongly. Same rules as forgetting. */
  async correctMemory(botId: string, memoryId: string, text: string): Promise<ActionResult> {
    let saved: MemoryItem | undefined;
    if (isDemoMode()) {
      const found = state.memories.find((m) => m.id === memoryId);
      if (found) saved = { ...found, text, updatedAt: now() };
    } else {
      try {
        saved = toMemory(await memoryApi.correct(state.org.id, botId, memoryId, text), botId);
      } catch (error) {
        return failure(error);
      }
    }
    if (!saved) return { ok: false, error: "That memory is already gone." };
    const corrected = saved;
    set((st) => ({ ...st, memories: st.memories.map((m) => (m.id === memoryId ? corrected : m)) }));
    updateMemoryList(botId, (items) => items.map((m) => (m.id === memoryId ? corrected : m)));
    supersedeMemoryLoads(botId);
    return { ok: true };
  },

  /** The bot forgets everything it learned, in every chat. Owners and admins only. */
  async forgetAllMemories(botId: string): Promise<ActionResult> {
    if (!isDemoMode()) {
      try {
        await memoryApi.forgetAll(state.org.id, botId);
      } catch (error) {
        return failure(error);
      }
    }
    set((st) => ({ ...st, memories: st.memories.filter((m) => m.botId !== botId) }));
    updateMemoryList(botId, () => []);
    supersedeMemoryLoads(botId);
    return { ok: true };
  },

  /**
   * Creates a bot and its DM, and returns the DM's id so the screen can open it.
   * MOCK: the bot speaks first, so the chat never opens empty.
   */
  async createBot(input: NewBotInput): Promise<ActionResult & { threadId?: string }> {
    if (isDemoMode()) return { ok: true, threadId: createMockBot(input) };
    const orgId = state.org.id;
    let bot: Bot;
    try {
      bot = toBot(await botApi.create(orgId, toApiBot(input)));
    } catch (error) {
      return failure(error);
    }
    set((st) => ({ ...st, bots: [...st.bots, bot] }));
    try {
      const dm = toThread(await threadApi.openDm(orgId, bot.id));
      set((st) => ({ ...st, threads: [...st.threads.filter((t) => t.id !== dm.id), dm] }));
      return { ok: true, threadId: dm.id };
    } catch {
      return { ok: false, error: `${bot.name} is on your team, but their chat didn't open. Reload the page to try again.` };
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
      set((st) => {
        const bots = st.bots.map((b) => (b.id === botId ? { ...saved, status: b.status, statusText: b.statusText } : b));
        return { ...st, bots, threads: st.threads.map((t) => withBotName(t, bots)) };
      });
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
        runs: st.runs.filter((r) => kept.has(r.threadId) && r.botId !== botId),
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

  /** Change your name or @handle. */
  async updateCurrentUser(patch: Partial<Pick<User, "name" | "handle">>): Promise<ActionResult> {
    let saved = patch;
    if (!isDemoMode()) {
      try {
        const { user } = await authApi.updateProfile(patch);
        saved = { name: user.name, handle: user.handle };
      } catch (error) {
        return failure(error);
      }
    }
    set((st) => ({ ...st, users: st.users.map((u) => (u.id === st.currentUserId ? { ...u, ...saved } : u)) }));
    return { ok: true };
  },

  /** Needs your current password. On the API, your other devices are signed out. */
  async changePassword(currentPassword: string, newPassword: string): Promise<ActionResult> {
    if (isDemoMode()) {
      const email = state.users.find((u) => u.id === state.currentUserId)?.email ?? "";
      if (state.passwords[email] !== currentPassword) return { ok: false, error: "Your current password isn't right." };
      if (newPassword.length < 8) return { ok: false, error: "Use at least 8 characters for your password." };
      set((st) => ({ ...st, passwords: { ...st.passwords, [email]: newPassword } }));
      return { ok: true };
    }
    try {
      await authApi.changePassword(currentPassword, newPassword);
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
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
    closeChatStreams();
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
      { memoryEnabled: true, ...input, id: botId, handle, status: "idle", statusText: "Just hired", connectionIds: [], createdAt: now(), spentThisMonthUsd: 0 },
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

/* ---------- Memory helpers ---------- */

/** The latest request per bot, so an older search answering late can't replace a newer one. */
const memoryRequests = new Map<string, number>();

function setMemoryList(botId: string, list: MemoryList) {
  set((st) => ({ ...st, memoryLists: { ...st.memoryLists, [botId]: list } }));
}

/**
 * After a memory change is saved: a load or search sent before it may answer with the memory as
 * it was (a forgotten one brought back), so its answer is ignored. A list still loading is loaded
 * again, so it settles on the state after the change.
 */
function supersedeMemoryLoads(botId: string) {
  if (isDemoMode()) return;
  memoryRequests.set(botId, (memoryRequests.get(botId) ?? 0) + 1);
  const list = state.memoryLists[botId];
  if (list?.status === "loading") void actions.loadMemories(botId, list.query);
}

/** Changes the items of a bot's open list, if it has one. */
function updateMemoryList(botId: string, change: (items: MemoryItem[]) => MemoryItem[]) {
  set((st) => {
    const list = st.memoryLists[botId];
    return list ? { ...st, memoryLists: { ...st.memoryLists, [botId]: { ...list, items: change(list.items) } } } : st;
  });
}

/** MOCK: a bot's memories, newest first, keeping those that contain `query`. */
function mockMemoriesOf(memories: MemoryItem[], botId: string, query: string) {
  const needle = query.trim().toLowerCase();
  return memories
    .filter((m) => m.botId === botId && m.text.toLowerCase().includes(needle))
    .sort((a, b) => (b.updatedAt ?? b.createdAt ?? "").localeCompare(a.updatedAt ?? a.createdAt ?? ""));
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

/** API only: whether this chat's messages have arrived. Undefined in the mock, which has them all. */
export const useThreadLoad = (threadId: string) => useStore(useCallback((s: State) => s.threadLoads[threadId], [threadId]));

/** True while a bot is replying in this chat, so the composer can offer Stop. */
export const useIsReplying = (threadId: string) =>
  useStore(useCallback((s: State) => s.runs.some((r) => r.threadId === threadId), [threadId]));

export const useThreadMessages = (threadId: string) =>
  useStore(useCallback((s: State) => s.messages.filter((m) => m.threadId === threadId), [threadId]));

export const useApproval = (id: string) => useStore(useCallback((s: State) => s.approvals.find((a) => a.id === id), [id]));

export type { ActiveRun };

/** API only: runs in this chat that stopped until a person checks on them. */
export const useRunsNeedingAttention = (threadId: string) =>
  useStore(useCallback((s: State) => s.runs.filter((r) => r.threadId === threadId && r.status === "needs_attention"), [threadId]));
export const usePendingApprovalCount = () => useStore(useCallback((s: State) => selectPendingApprovals(s).length, []));

export const useBotRoutines = (botId?: string) =>
  useStore(useCallback((s: State) => s.routines.filter((r) => r.botId === botId), [botId]));

/** A bot's memories as last loaded with `actions.loadMemories`; undefined until then. */
export const useMemoryList = (botId?: string) =>
  useStore(useCallback((s: State) => (botId ? s.memoryLists[botId] : undefined), [botId]));

/** Whether bots can remember here (null while the API is asked). */
export const useMemoryStatus = () => useStore(useCallback((s: State) => s.memoryStatus, []));

/* Whole-collection hooks for the app pages (marketplace, settings, approvals…). */
export const useBots = () => useStore(useCallback((s: State) => s.bots, []));
export const useBotsLoading = () => useStore(useCallback((s: State) => s.botsLoading, []));
export const useUsers = () => useStore(useCallback((s: State) => s.users, []));
export const useInvitations = () => useStore(useCallback((s: State) => s.invitations, []));
export const useModels = () => useStore(useCallback((s: State) => s.models, []));
export const useModelProviders = () => useStore(useCallback((s: State) => s.modelProviders, []));
/** Connected providers whose models couldn't be listed just now. */
export const useModelProblems = () => useStore(useCallback((s: State) => s.modelProblems, []));
/** API only: true while providers and models are on their way. */
export const useModelsLoading = () => useStore(useCallback((s: State) => s.modelsLoading, []));
export const useTemplates = () => useStore(useCallback((s: State) => s.templates, []));
export const useRoutines = () => useStore(useCallback((s: State) => s.routines, []));
export const useUsage = () => useStore(useCallback((s: State) => s.usage, []));
export const useUsageLoading = () => useStore(useCallback((s: State) => s.usageLoading, []));
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
