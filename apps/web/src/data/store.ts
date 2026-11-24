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
 *   keys, your own keys (My keys) and live model lists; the org's security ceiling; new
 *   organizations; what each bot remembers (Memory), loaded per bot; and Usage &
 *   budgets: daily spend, each bot's spend this month and the org's budget; and Routines:
 *   listed with the org, created, edited, switched on and off, run now and removed; and
 *   bots' Files: where the org keeps them (Settings → Computers) and each bot's list; and
 *   each bot's Browser: watching it and taking over. Apps
 *   aren't all on the API yet, so some stay mock.
 * - Not set (tests, e2e, demos): everything is the in-memory mock, with fake bot replies.
 * Guest mode ("Explore the demo") uses the mock in either case, so people can look
 * around without an account; it never calls the API.
 * Screens can't tell the difference: they use the hooks and actions below either way.
 */
import { useCallback, useRef, useSyncExternalStore } from "react";
import { makeHandle } from "@/lib/handle";
import { parseMentions } from "@/lib/mentions";
import { HOP_LIMIT, chainStoppedText, routeMessage, type BotReply, type ChatBots } from "@/lib/mention-routing";
import { previewFromArgs } from "@/lib/args-form";
import { strictestLevel } from "@/lib/security-ceiling";
import { rememberOAuthReturn } from "@/lib/connections";
import { browser } from "@/lib/navigate";
import { approvalApi, authApi, botApi, browserApi, connectionApi, fileApi, inviteApi, mcpApi, memoryApi, modelApi, orgApi, pluginApi, routineApi, runApi, templateApi, threadApi, usageApi } from "./api/botdesk";
import { ApiError, apiBaseUrl } from "./api/client";
import { toAccountConnection, toApiBot, toApproval, toBot, toBotBrowser, toBotFile, toBrowserProvider, toFileStorage, toInvitation, toMcpServer, toMemory, toMemoryStatus, toMessage, toModel, toModelProvider, toOrg, toRoutine, toTemplate, toThread, toUsage, toUser } from "./api/map";
import { applyRunEvent, typingId, upsertApproval, withActiveRuns, withPreview, withWaitingApprovals, type ActiveRun } from "./api/run-events";
import type { ApiMe, ApiMessage, ApiRunEvent, ApiThread, ApiThreadRuns } from "./api/types";
import { isTaskOpen, taskPreview, withTaskChangeIn, type TaskChange } from "@/lib/tasks";
import * as chiefDemo from "./mock/chief-demo";
import * as mock from "./mock/fixtures";
import type {
  AccountConnection, AccountConnectionList, Approval, ApprovalStatus, Bot, BotBrowser, BotFile, BotFileList, BrowserInput, BrowserLoad, BrowserProviderLoad, BotToolChange, BotTools, ConnectionOwner, Invitation, McpServerInput, McpServerList, McpToolChoice, MemoryItem, MemoryList, MemoryStatus, Membership, Message, Model, ModelListProblem, ModelProvider, Org,
  Participant, PluginList, Routine, SecurityLevel, ServerConnectorList, StorageLoad, TemplateList, Thread, UsageSummary, User,
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
  /** One of `botIds`; left out, the first bot picked leads. */
  leadBotId?: string;
}

/** What you fill in to create a routine. */
export type NewRoutineInput = Pick<Routine, "botId" | "name" | "description" | "schedule" | "steps" | "enabled">
  /* API: when it runs (5 fields) and in which time zone (defaults to this browser's). */
  & Partial<Pick<Routine, "cron" | "timezone">>;

/** "unknown" until the browser has checked for a saved session (first render, server). */
export type AuthStatus = "unknown" | "signed-in" | "signed-out";
/** Who may create an account on this server (the API's SIGNUP_MODE). */
export type SignUpMode = "open" | "invite-only" | "closed";

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
const isDemo = (s: Pick<State, "guest">) => apiBaseUrl() === "" || s.guest;
export const isDemoMode = () => isDemo(state);

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
  /** Bot replies in progress. The mock fakes most replies without these; its Chief demo has one. */
  runs: ActiveRun[];
  /** API only: runs seen finish, so a late event can't revive one (see api/run-events.ts). */
  endedRunIds: string[];
  /** The newest state heard for each handed-off Task (ADR 0014), so its card never moves backwards. */
  taskChanges: Record<string, TaskChange>;
  approvals: Approval[];
  connectors: typeof mock.connectors;
  /** API only: the plugins the server loaded (Connect apps). The demo has none. */
  plugins: PluginList;
  connections: typeof mock.connections;
  /** Connect apps on the API: the server's connectors (GET /connectors). The demo uses `connectors`. */
  serverConnectors: ServerConnectorList;
  /** Accounts connected to connectors, as the API shows them (the demo: Ali's Gmail). */
  accounts: AccountConnectionList;
  /** The organization's MCP servers (API only; the demo has none). */
  mcpServers: McpServerList;
  /** Each bot's Tools tab (which plugins it uses, through which account), by bot id. */
  botTools: Record<string, BotTools>;
  routines: typeof mock.routines;
  /** API only: true while the org's routines are on their way. */
  routinesLoading: boolean;
  /** Models & keys: the live model list of every connected provider, and the providers themselves. */
  models: Model[];
  modelProviders: ModelProvider[];
  /** My keys: your own key per built-in provider in this org, which only your runs use. Null until loaded. */
  myKeys: ModelProvider[] | null;
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
  /** The marketplace. On the API it loads once you're signed in (the same for every organization). */
  templates: TemplateList;
  /** Settings → Computers: where the org keeps bots' files. */
  storage: StorageLoad;
  /** Each bot's files as last loaded, by bot id. The demo starts with Inbox Manager's. */
  fileLists: Record<string, BotFileList>;
  /** Each bot's browser as last seen, by bot id (the bot details' Computer tab). */
  browsers: Record<string, BrowserLoad>;
  /** Settings → Computers: where the org's bots' browsers run. */
  browserProvider: BrowserProviderLoad;
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
    taskChanges: {},
    approvals: mock.approvals,
    connectors: mock.connectors,
    plugins: { status: "ready", items: [] },
    connections: mock.connections,
    serverConnectors: { status: "ready", items: [] },
    accounts: { status: "ready", items: mock.accountConnections },
    mcpServers: { status: "ready", items: [] },
    botTools: {},
    routines: mock.routines,
    routinesLoading: false,
    models: mock.models,
    modelProviders: mock.modelProviders,
    // MOCK: every built-in provider of the demo, none with a key of yours yet.
    myKeys: notConnected(mock.modelProviders.filter((p) => p.kind !== "custom")),
    modelProblems: [],
    modelsLoading: false,
    memories: mock.memories,
    memoryLists: {},
    memoryStatus: { enabled: true },
    usage: mockUsage(),
    usageLoading: false,
    spentByBot: {},
    templates: { status: "ready", items: mock.templates },
    storage: { status: "ready", current: mock.storage },
    fileLists: demoFileLists(),
    browsers: {},
    browserProvider: { status: "ready", current: { provider: "local", projectId: "", localAvailable: true } },
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
    org: { id: "", name: "", slug: "", defaultSecurityLevel: "ask-before-acting", maxSecurityLevel: "autonomous" },
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
    routinesLoading: true,
    plugins: { status: "loading", items: [] },
    serverConnectors: { status: "loading", items: [] },
    accounts: { status: "loading", items: [] },
    mcpServers: { status: "loading", items: [] },
    botTools: {},
    memories: [],
    memoryStatus: null,
    models: [],
    modelProviders: [],
    myKeys: null,
    usage: EMPTY_USAGE,
    usageLoading: true,
    templates: { status: "loading", items: [] },
    storage: { status: "loading" },
    fileLists: {},
    browsers: {},
    browserProvider: { status: "loading" },
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
    taskChanges: {},
    approvals: [],
    models: [],
    modelProviders: [],
    myKeys: null,
    modelProblems: [],
    modelsLoading: true,
    routines: [],
    routinesLoading: true,
    plugins: { status: "loading", items: [] },
    serverConnectors: { status: "loading", items: [] },
    accounts: { status: "loading", items: [] },
    mcpServers: { status: "loading", items: [] },
    botTools: {},
    memories: [],
    memoryLists: {},
    memoryStatus: null,
    botsLoading: true,
    usage: EMPTY_USAGE,
    usageLoading: true,
    spentByBot: {},
    // The same for every org, but the demo's never stay (the API's are fetched again, a small list).
    templates: { status: "loading", items: [] },
    storage: { status: "loading" },
    fileLists: {},
    browsers: {},
    browserProvider: { status: "loading" },
  }));
  void loadOrgPeople(org);
  void loadBotsAndChats(org);
  void loadModelCatalog(org.id);
  void loadUsage(org.id);
  void loadRoutines(org.id);
  void loadTemplates();
}

/** The marketplace's templates (`GET /templates`): the same for every org on this server. */
async function loadTemplates() {
  set((st) => ({ ...st, templates: { ...st.templates, status: "loading" } }));
  const listed = await templateApi.list().catch(() => null);
  if (isDemoMode()) return; // left for the demo meanwhile: it has its own
  set((st) => ({ ...st, templates: listed ? { status: "ready", items: listed.map(toTemplate) } : { ...st.templates, status: "error" } }));
}

/** The org's routines (each with its schedule, next run and how the last one went). */
async function loadRoutines(orgId: string) {
  const routines = await routineApi.list(orgId).catch(() => null);
  set((st) => (st.org.id !== orgId ? st : { ...st, routines: routines?.map(toRoutine) ?? st.routines, routinesLoading: false }));
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

  /** With `inviteToken` (from an invite link) the new account joins that organization instead of getting its own. */
  async signUp(input: { name: string; email: string; password: string; inviteToken?: string }): Promise<ActionResult> {
    if (state.guest) leaveGuestMode();
    if (isDemoMode()) return mockAuth.signUp(input); // MOCK: no invites, so the token is ignored.
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

  /** The security level new bots start at. Owners and admins; the API refuses members. */
  async setDefaultSecurityLevel(level: SecurityLevel): Promise<ActionResult> {
    let saved = level;
    if (!isDemoMode()) {
      try {
        saved = toOrg(await orgApi.update(state.org.id, { defaultSecurityLevel: level })).defaultSecurityLevel;
      } catch (error) {
        return failure(error);
      }
    }
    set((st) => ({
      ...st,
      org: { ...st.org, defaultSecurityLevel: saved },
      orgs: st.orgs.map((o) => (o.id === st.org.id ? { ...o, defaultSecurityLevel: saved } : o)),
    }));
    return { ok: true };
  },

  /**
   * The highest level any bot here may act at (ADR 0004). Owners and admins; the API refuses
   * members. Lowering it below the default for new bots lowers the default too.
   */
  async setMaxSecurityLevel(level: SecurityLevel): Promise<ActionResult> {
    let saved: Pick<Org, "maxSecurityLevel" | "defaultSecurityLevel"> = {
      maxSecurityLevel: level,
      defaultSecurityLevel: strictestLevel(state.org.defaultSecurityLevel, level),
    };
    if (!isDemoMode()) {
      try {
        const org = toOrg(await orgApi.update(state.org.id, { maxSecurityLevel: level }));
        saved = { maxSecurityLevel: org.maxSecurityLevel, defaultSecurityLevel: org.defaultSecurityLevel };
      } catch (error) {
        return failure(error);
      }
    }
    set((st) => ({ ...st, org: { ...st.org, ...saved }, orgs: st.orgs.map((o) => (o.id === st.org.id ? { ...o, ...saved } : o)) }));
    return { ok: true };
  },

  /** A new organization you own, which then becomes the current one. Needs an account (not the demo). */
  async createOrg(name: string): Promise<ActionResult> {
    if (isDemoMode()) return { ok: false, error: "Creating organizations needs an account. Sign up to make your own." };
    try {
      const created: Membership = { ...toOrg(await orgApi.create({ name: name.trim() })), role: "owner" };
      set((st) => ({ ...st, orgs: [...st.orgs.filter((o) => o.id !== created.id), created] }));
      enterOrg(created);
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
/**
 * When each chat was last marked read here, so a chat list asked for before that can't undo it.
 * Times are a counter, not the clock: two things in the same millisecond still have an order.
 */
let clock = 0;
const tick = () => ++clock;
const readAt = new Map<string, number>();
/** When each chat left this browser's list (you left a group, its bot was removed), likewise. */
const removedAt = new Map<string, number>();
/** Each open chat's newest event id when it opened: its stream's events up to there are replays. */
const replayedUpTo = new Map<string, number>();

function closeChatStreams() {
  chatStreams.forEach((close) => close());
  chatStreams.clear();
  // Another org's chats, or a fresh start.
  readAt.clear();
  removedAt.clear();
  replayedUpTo.clear();
}

/** Chats that are no longer yours leave the list now; a chat list asked for before this won't bring them back. */
function dropThreads(st: State, ids: Set<string>): State {
  ids.forEach((threadId) => removedAt.set(threadId, tick()));
  return { ...st, threads: st.threads.filter((t) => !ids.has(t.id)) };
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
  const unread = event.kind === "message_saved" && isNewFromSomeoneElse(event.threadId, event.data.message);
  set((st) => (st.org.id === orgId ? withRunStatus({ ...st, ...applyRunEvent(st, event) }) : st));
  if (unread) countUnread(event.threadId);
  if (event.kind === "thread_updated" && !event.data.thread.participants.some((p) => p.type === "user" && p.id === state.currentUserId)) {
    // A change that left you out. Heard live, you were removed: the group goes now (the API ends
    // the stream too). Replayed as the chat opened, it's an old change: you may have been added
    // back since, so it stays. Either way the chat list has the last word (and brings the group
    // back if you were added back).
    if (event.id > (replayedUpTo.get(event.threadId) ?? 0)) set((st) => (st.org.id === orgId ? dropThreads(st, new Set([event.threadId])) : st));
    void actions.refreshChats();
  }
  if (event.kind === "run_finished" || event.kind === "run_failed") scheduleUsageRefresh(orgId);
  // Someone asked or decided: the sidebar count may be behind on other chats too.
  if (event.kind === "approval_requested" || event.kind === "approval_decided") void approvalActions.refreshPendingApprovals();
}

/* ---------- Unread counts ----------
 * The API counts what you haven't read (`unread` on each chat). The chat you're looking at, in a
 * visible tab, is read: opening it, coming back to the tab and each new message there tell the
 * API. Elsewhere, a new message heard on a stream adds one; `refreshChats` (polled by the shell)
 * brings in the rest, since only open chats have a stream.
 */
let viewedThreadId: string | null = null;

const isLookingAt = (threadId: string) => viewedThreadId === threadId && document.visibilityState === "visible";

/** A saved message we haven't counted yet (a replay or your own doesn't count). A streamed reply is
 *  already in the store while it's written, so only a saved copy means it was seen before. While a
 *  chat loads, its stream replays messages the page is about to bring, so nothing counts then. */
function isNewFromSomeoneElse(threadId: string, message: ApiMessage) {
  if (state.threadLoads[threadId]?.status === "loading") return false;
  const mine = message.author.type === "user" && message.author.id === state.currentUserId;
  return !mine && !state.messages.some((m) => m.id === message.id && m.status !== "streaming");
}

function countUnread(threadId: string) {
  if (isLookingAt(threadId)) return actions.markRead(threadId);
  set((st) => ({ ...st, threads: st.threads.map((t) => (t.id === threadId ? { ...t, unread: t.unread + 1 } : t)) }));
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
  const running = runs.find((r) => r.status !== "waiting_handoff");
  if (running) return { status: "working", statusText: running.messageId ? "Replying…" : "Thinking…" };
  return runs.length > 0 ? { status: "working", statusText: WAITING_ON_TEAMMATES } : undefined;
}

const WAITING_ON_TEAMMATES = "Waiting on teammates";

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
    set((st) => {
      // An update heard on the stream may be newer than the page's cards.
      const page = Object.values(st.taskChanges).reduce(withTaskChangeIn, apiPage.map(toMessage));
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
   * Call when a chat is on screen; call what it returns when it leaves. The chat is marked read
   * now, whenever the tab becomes visible again, and as messages arrive while you look at it.
   */
  viewThread(threadId: string): () => void {
    viewedThreadId = threadId;
    // A chat opened in a background tab isn't read until you look at it (`onVisible`).
    if (isLookingAt(threadId)) actions.markRead(threadId);
    const onVisible = () => {
      if (isLookingAt(threadId)) actions.markRead(threadId);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      if (viewedThreadId === threadId) viewedThreadId = null;
    };
  },

  /**
   * Your chats again from the API: new counts, previews, groups you were added to or removed from.
   * The list may be a moment old when it lands, so it never undoes what happened meanwhile here:
   * a chat started while it was on its way stays (it's not in the list yet), a chat that left
   * since it was asked for stays gone, a chat read since stays read, and a newer message heard on
   * a stream keeps its preview.
   */
  async refreshChats(): Promise<void> {
    if (isDemoMode() || state.authStatus !== "signed-in") return;
    const orgId = state.org.id;
    const askedAt = tick();
    const known = new Set(state.threads.map((t) => t.id));
    const apiThreads = await threadApi.list(orgId).catch(() => null);
    if (!apiThreads) return;
    set((st) => {
      if (st.org.id !== orgId || st.botsLoading) return st; // the org's first load brings them all
      const goneSince = (id: string) => (removedAt.get(id) ?? 0) > askedAt;
      const listed = apiThreads.filter((t) => !goneSince(t.id)).map((t) => withBotName(toThread(t), st.bots));
      const startedSince = st.threads.filter((t) => !known.has(t.id) && !listed.some((l) => l.id === t.id));
      const threads = listed.map((fresh) => {
        const here = st.threads.find((t) => t.id === fresh.id);
        const newerHere = here !== undefined && Date.parse(here.lastMessageAt) > Date.parse(fresh.lastMessageAt);
        const readSince = isLookingAt(fresh.id) || (readAt.get(fresh.id) ?? 0) > askedAt;
        return {
          ...fresh,
          ...(newerHere ? { lastMessageAt: here.lastMessageAt, lastMessagePreview: here.lastMessagePreview } : {}),
          unread: readSince ? 0 : newerHere ? Math.max(fresh.unread, here.unread) : fresh.unread,
        };
      });
      return { ...st, threads: [...threads, ...startedSince] };
    });
  },

  /** Rename a group. Its creator, owners and admins may (`useCanChangeLead`, the same rule). */
  async renameGroup(threadId: string, title: string): Promise<ActionResult> {
    const name = title.trim();
    if (!name) return { ok: false, error: "Give the group a name." };
    if (isDemoMode()) return putGroup(threadId, (t) => ({ ...t, title: name }));
    return saveGroup(() => threadApi.rename(state.org.id, threadId, name));
  },

  /** Add people and bots to a group. Ones already in it are left as they are. */
  async addToGroup(threadId: string, add: { userIds: string[]; botIds: string[] }): Promise<ActionResult> {
    if (isDemoMode()) {
      return putGroup(threadId, (t) => {
        const added = [...add.userIds.map((id) => ({ type: "user" as const, id })), ...add.botIds.map((id) => ({ type: "bot" as const, id }))];
        const fresh = added.filter((p) => !t.participants.some((q) => q.type === p.type && q.id === p.id));
        return { ...t, participants: [...t.participants, ...fresh] };
      });
    }
    return saveGroup(() => threadApi.addParticipants(state.org.id, threadId, add));
  },

  /**
   * Take a person or a bot out of a group. Removing the lead bot leaves it without a lead.
   * Taking yourself out is leaving (`leaveGroup`): the group leaves your list.
   */
  async removeFromGroup(threadId: string, who: Participant): Promise<ActionResult> {
    if (isDemoMode()) {
      if (who.type === "user" && who.id === state.currentUserId) {
        set((st) => dropThreads(st, new Set([threadId])));
        return { ok: true };
      }
      return putGroup(threadId, (t) => ({
        ...t,
        participants: t.participants.filter((p) => !(p.type === who.type && p.id === who.id)),
        leadBotId: who.type === "bot" && t.leadBotId === who.id ? undefined : t.leadBotId,
      }));
    }
    return saveGroup(() => threadApi.removeParticipant(state.org.id, threadId, who.type, who.id));
  },

  /** Leave a group (anyone in it may). It leaves your list; one you were the last person in is deleted. */
  leaveGroup(threadId: string): Promise<ActionResult> {
    return actions.removeFromGroup(threadId, { type: "user", id: state.currentUserId });
  },
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
      replayedUpTo.set(threadId, active?.lastEventId ?? 0); // without the list, the stream starts from now
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

  /** Stop the bot replies in progress in this chat. In the demo, only the Chief demo can be stopped. */
  async stopReplies(threadId: string): Promise<ActionResult> {
    const runs = state.runs.filter((r) => r.threadId === threadId);
    if (isDemoMode()) {
      runs.forEach((r) => stopMockRun(r.id));
      return { ok: true };
    }
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
    if (isDemoMode()) {
      stopMockRun(runId);
      return { ok: true };
    }
    try {
      await runApi.cancel(state.org.id, runId);
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /**
   * Answer a run that needs attention: the call it stopped on was done, or wasn't. The bot then
   * carries on (it shows as working at once; the stream follows) and never repeats the call by
   * itself. In the mock it's over at once.
   */
  async resolveRun(runId: string, outcome: "done" | "not_done"): Promise<ActionResult> {
    if (isDemoMode()) {
      setMockRun(null, runId);
      return { ok: true };
    }
    try {
      await runApi.resolve(state.org.id, runId, outcome);
      set((st) =>
        withRunStatus({
          ...st,
          runs: st.runs.map((r) => (r.id === runId && r.status === "needs_attention" ? { ...r, status: "running", error: undefined } : r)),
        }),
      );
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
    const leadBotId = input.leadBotId && input.botIds.includes(input.leadBotId) ? input.leadBotId : input.botIds[0];

    let thread: Thread;
    if (isDemoMode()) {
      thread = {
        id: `t_${id()}`, kind: "group", title, leadBotId, createdBy: state.currentUserId,
        participants: [
          { type: "user", id: state.currentUserId },
          ...userIds.map((u) => ({ type: "user" as const, id: u })),
          ...input.botIds.map((b) => ({ type: "bot" as const, id: b })),
        ],
        lastMessageAt: now(), lastMessagePreview: "", unread: 0,
      };
    } else {
      try {
        thread = toThread(await threadApi.createGroup(state.org.id, { title, botIds: input.botIds, userIds, leadBotId }));
      } catch (error) {
        return failure(error);
      }
    }
    set((st) => ({ ...st, threads: [thread, ...st.threads.filter((t) => t.id !== thread.id)] }));
    return { ok: true, threadId: thread.id };
  },

  /**
   * Changes a group's lead (the bot that answers messages that @mention no bot), or clears it
   * with null. The group's creator, owners and admins may (`useCanChangeLead`).
   */
  async setGroupLead(threadId: string, botId: string | null): Promise<ActionResult> {
    const orgId = state.org.id;
    const putLead = (leadBotId: string | undefined) =>
      set((st) => ({
        ...st,
        threads: st.threads.map((t) => (t.id === threadId ? { ...t, leadBotId } : t)),
      }));
    if (isDemoMode()) {
      putLead(botId ?? undefined);
      return { ok: true };
    }
    try {
      const saved = toThread(await threadApi.setLead(orgId, threadId, botId));
      if (state.org.id === orgId) putLead(saved.leadBotId);
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },
};

/** MOCK: change a group in the store. */
function putGroup(threadId: string, change: (thread: Thread) => Thread): ActionResult {
  set((st) => ({ ...st, threads: st.threads.map((t) => (t.id === threadId ? change(t) : t)) }));
  return { ok: true };
}

/** Save a change to a group on the API, and show the group as it answers (your unread count stays). */
async function saveGroup(save: () => Promise<ApiThread>): Promise<ActionResult> {
  const orgId = state.org.id;
  try {
    const saved = toThread(await save());
    const stillIn = saved.participants.some((p) => p.type === "user" && p.id === state.currentUserId);
    set((st) => {
      if (st.org.id !== orgId) return st;
      if (!stillIn) return dropThreads(st, new Set([saved.id]));
      return { ...st, threads: st.threads.map((t) => (t.id === saved.id ? { ...saved, unread: t.unread, pinned: t.pinned } : t)) };
    });
    return { ok: true };
  } catch (error) {
    return failure(error);
  }
}

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

  /** My keys in the current org (Settings → Models & keys). The demo starts with none. */
  async loadMyKeys(): Promise<void> {
    const orgId = state.org.id;
    if (isDemoMode()) return; // the demo's are in its seed
    const keys = await modelApi.myKeys(orgId).catch(() => null);
    set((st) => (st.org.id === orgId ? { ...st, myKeys: keys?.map(toModelProvider) ?? st.myKeys ?? [] } : st));
  },

  /** Your own key for a built-in provider (any member). Checked live on the API; once saved, only its last 4 characters come back. */
  async saveMyKey(providerId: string, apiKey: string): Promise<ActionResult> {
    const orgId = state.org.id;
    let saved: ModelProvider;
    if (isDemoMode()) {
      const key = apiKey.trim();
      if (key.startsWith("bad")) return { ok: false, error: "That key didn't work: 401: Incorrect API key provided." };
      const provider = state.myKeys?.find((p) => p.id === providerId);
      if (!provider) return { ok: false, error: "We don't support that provider." };
      const hint = keyHintOf(key);
      saved = { ...provider, connected: true, source: "member", status: "ok", lastVerifiedAt: now(), ...(hint ? { keyHint: hint } : {}) };
    } else {
      try {
        saved = toModelProvider(await modelApi.saveMyKey(orgId, providerId, apiKey.trim()));
      } catch (error) {
        return failure(error);
      }
      void loadModelCatalog(orgId); // models only your key reaches show up for you too
    }
    set((st) => (st.org.id === orgId ? { ...st, myKeys: withProvider(st.myKeys ?? [], saved) } : st));
    return { ok: true };
  },

  /** Check your own saved key again, like `testProviderKey` for the org's. `ok: false` carries the provider's reason. */
  async testMyKey(providerId: string): Promise<ActionResult> {
    const orgId = state.org.id;
    if (isDemoMode()) {
      set((st) => ({ ...st, myKeys: (st.myKeys ?? []).map((p) => (p.id === providerId ? { ...p, status: "ok", lastVerifiedAt: now() } : p)) }));
      return { ok: true };
    }
    try {
      const result = await modelApi.testMyKey(orgId, providerId);
      set((st) => (st.org.id === orgId ? { ...st, myKeys: withProvider(st.myKeys ?? [], toModelProvider(result.provider)) } : st));
      return result.ok ? { ok: true } : { ok: false, error: result.error ?? "That key didn't work." };
    } catch (error) {
      return failure(error);
    }
  },

  /** Remove your own key. Your runs go back to the org's key, if it has one. */
  async removeMyKey(providerId: string): Promise<ActionResult> {
    const orgId = state.org.id;
    if (!isDemoMode()) {
      try {
        await modelApi.removeMyKey(orgId, providerId);
      } catch (error) {
        return failure(error);
      }
      void loadModelCatalog(orgId);
    }
    set((st) => {
      if (st.org.id !== orgId) return st;
      return { ...st, myKeys: (st.myKeys ?? []).map((p) => (p.id === providerId ? notConnected([p])[0] : p)) };
    });
    return { ok: true };
  },
};

/** Providers as they look without a key: no hint, no source, no check. (Hoisted: the demo's seed uses it.) */
function notConnected(providers: ModelProvider[]): ModelProvider[] {
  return providers.map(({ id, kind, name, hint }) => ({ id, kind, name, hint, connected: false }));
}

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

/* ---------- Files and storage (ADR 0017) ----------
 * Where the org keeps bots' files (Settings → Computers) and each bot's files (its Computer tab).
 * On the API an S3 secret goes in once and never comes back: the store only holds the access key's
 * last 4 characters. MOCK: storage starts as Local and an S3 bucket "works" unless its secret starts
 * with "bad"; uploads and deletes happen in memory, and files open from blob: URLs.
 */

/** What you fill in to choose storage. An empty secret keeps the saved one (storage that is already S3, or already Cloudinary). */
export type StorageInput =
  | { provider: "local" }
  | { provider: "s3"; s3: { endpoint: string; region: string; bucket: string; prefix: string; accessKeyId: string; secretAccessKey: string } }
  | { provider: "cloudinary"; cloudinary: { cloudName: string; apiKey: string; apiSecret: string } };

/** The API's FILE_MAX_MB, for the demo's uploads. */
const FILE_MAX_MB = 25;

/** The latest list request per bot, so an older one answering late can't undo an upload or a delete. */
const fileLoads = new Map<string, number>();

/** MOCK: the demo's files, one list per bot. (Hoisted: the demo's seed uses it.) */
function demoFileLists(): Record<string, BotFileList> {
  const lists: Record<string, BotFileList> = {};
  for (const file of mock.files) {
    const botId = file.botId ?? "";
    lists[botId] = { status: "ready", items: [...(lists[botId]?.items ?? []), file] };
  }
  return lists;
}

/** MOCK: a link the browser can open for a demo file. None where blob: URLs don't exist (tests). */
const canMakeDemoUrls = () => typeof URL.createObjectURL === "function";
const demoFileUrl = (blob: Blob) => (canMakeDemoUrls() ? URL.createObjectURL(blob) : "");
function forgetDemoUrl(file?: BotFile) {
  if (file?.url.startsWith("blob:")) URL.revokeObjectURL(file.url);
}

function setFileList(botId: string, list: BotFileList) {
  set((st) => ({ ...st, fileLists: { ...st.fileLists, [botId]: list } }));
}

/** Changes the items of a bot's list, if it has one. */
function updateFileList(botId: string, change: (items: BotFile[]) => BotFile[]) {
  set((st) => {
    const list = st.fileLists[botId];
    return list ? { ...st, fileLists: { ...st.fileLists, [botId]: { ...list, items: change(list.items) } } } : st;
  });
}

/** After an upload or delete: a list sent for before it is ignored, and one still loading is asked for again. */
function supersedeFileLoads(botId: string) {
  if (isDemoMode()) return;
  fileLoads.set(botId, (fileLoads.get(botId) ?? 0) + 1);
  if (state.fileLists[botId]?.status === "loading") void fileActions.loadFiles(botId);
}

/** A saved file in its list: in place of the one at its path (saving a path again replaces it), in path order. */
function withFile(items: BotFile[], saved: BotFile): BotFile[] {
  const others = items.filter((f) => f.id !== saved.id && f.path !== saved.path);
  return [...others, saved].sort((a, b) => a.path.localeCompare(b.path));
}

/** MOCK: the bot's folder gets the file, at its name, with the API's size limit. */
function saveMockFile(botId: string, file: File): { ok: true; file: BotFile } | { ok: false; error: string } {
  if (file.size > FILE_MAX_MB * 1024 * 1024) return { ok: false, error: `That file is too big: files can be up to ${FILE_MAX_MB} MB.` };
  const replaced = state.fileLists[botId]?.items.find((f) => f.path === file.name);
  forgetDemoUrl(replaced);
  const at = now();
  const handle = state.bots.find((b) => b.id === botId)?.handle ?? "bot";
  return {
    ok: true,
    file: {
      id: replaced?.id ?? `file_${id()}`, botId, path: file.name, folder: `botdesk/${handle}`, contentType: file.type || "application/octet-stream",
      sizeBytes: file.size, available: true, createdAt: replaced?.createdAt ?? at, updatedAt: at, url: demoFileUrl(file),
    },
  };
}

/** MOCK: "checks" the bucket like the API would, then switches to it (or back to Local). */
function saveMockStorage(input: StorageInput): ActionResult {
  const current = state.storage.current;
  if (input.provider === "local") {
    if (current && !current.localAvailable) return { ok: false, error: "This server doesn't keep files itself." };
    set((st) => ({ ...st, storage: { status: "ready", current: { provider: "local", localAvailable: current?.localAvailable ?? true } } }));
    return { ok: true };
  }
  if (input.provider === "cloudinary") {
    const { cloudName, apiKey, apiSecret } = input.cloudinary;
    if (!/^[A-Za-z0-9_-]{1,100}$/.test(cloudName.trim()) || apiKey.trim().length < 4) return { ok: false, error: "Fill in the Cloudinary details." };
    if (!apiSecret.trim() && current?.provider !== "cloudinary") return { ok: false, error: "Add the API secret." };
    if (apiSecret.trim().startsWith("bad")) return { ok: false, error: `Cloudinary refused the keys for ${cloudName.trim()}. Check the API key and secret.` };
    const cloudinary = { cloudName: cloudName.trim(), apiKeyHint: apiKey.trim().slice(-4) };
    set((st) => ({ ...st, storage: { status: "ready", current: { provider: "cloudinary", cloudinary, localAvailable: current?.localAvailable ?? true, checkedAt: now() } } }));
    return { ok: true };
  }
  const { endpoint, region, bucket, prefix, accessKeyId, secretAccessKey } = input.s3;
  if (!region.trim() || bucket.trim().length < 3 || accessKeyId.trim().length < 4) return { ok: false, error: "Fill in the bucket's details." };
  if (!secretAccessKey.trim() && current?.provider !== "s3") return { ok: false, error: "Add the secret access key." };
  if (secretAccessKey.trim().startsWith("bad")) {
    return { ok: false, error: "Couldn't write to the bucket: the access key or secret is wrong (403 Forbidden)." };
  }
  const s3 = {
    endpoint: endpoint.trim().replace(/\/+$/, ""), region: region.trim(), bucket: bucket.trim(),
    prefix: prefix.trim().replace(/^\/+|\/+$/g, ""), accessKeyHint: accessKeyId.trim().slice(-4),
  };
  set((st) => ({ ...st, storage: { status: "ready", current: { provider: "s3", s3, localAvailable: current?.localAvailable ?? true, checkedAt: now() } } }));
  return { ok: true };
}

const fileActions = {
  /** Where the org keeps files. The demo's is in its seed. */
  async loadStorage(): Promise<void> {
    if (isDemoMode()) return;
    const orgId = state.org.id;
    const loaded = await fileApi.storage(orgId).catch(() => null);
    set((st) => {
      if (st.org.id !== orgId) return st;
      return { ...st, storage: loaded ? { status: "ready", current: toFileStorage(loaded) } : { ...st.storage, status: "error" } };
    });
  },

  /** Choose Local or an S3-compatible bucket (owners and admins). The API checks it live first, which can take a few seconds. */
  async saveStorage(input: StorageInput): Promise<ActionResult> {
    if (isDemoMode()) return saveMockStorage(input);
    const orgId = state.org.id;
    const body = input.provider === "local" ? input : input.provider === "cloudinary" ? {
      provider: input.provider,
      cloudinary: {
        cloudName: input.cloudinary.cloudName.trim(), apiKey: input.cloudinary.apiKey.trim(),
        ...(input.cloudinary.apiSecret.trim() ? { apiSecret: input.cloudinary.apiSecret.trim() } : {}),
      },
    } : {
      provider: input.provider,
      s3: {
        endpoint: input.s3.endpoint.trim(), region: input.s3.region.trim(), bucket: input.s3.bucket.trim(),
        prefix: input.s3.prefix.trim(), accessKeyId: input.s3.accessKeyId.trim(),
        ...(input.s3.secretAccessKey.trim() ? { secretAccessKey: input.s3.secretAccessKey.trim() } : {}),
      },
    };
    try {
      const saved = toFileStorage(await fileApi.chooseStorage(orgId, body));
      // Files saved before stay where they were, so whether each can be opened changed: lists load again.
      set((st) => (st.org.id === orgId ? { ...st, storage: { status: "ready", current: saved }, fileLists: {} } : st));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** A bot's files, by path. */
  async loadFiles(botId: string): Promise<void> {
    if (isDemoMode()) {
      if (!state.fileLists[botId]) setFileList(botId, { status: "ready", items: [] });
      if (!canMakeDemoUrls()) return;
      // The demo's own files get their links the first time they're shown (blob: URLs exist only in the browser).
      return updateFileList(botId, (items) => items.map((f) => {
        const text = mock.fileContents[f.id];
        return f.url || !f.available || text === undefined ? f : { ...f, url: demoFileUrl(new Blob([text], { type: f.contentType })) };
      }));
    }
    const orgId = state.org.id;
    const request = (fileLoads.get(botId) ?? 0) + 1;
    fileLoads.set(botId, request);
    const current = () => fileLoads.get(botId) === request && state.org.id === orgId;
    setFileList(botId, { status: "loading", items: state.fileLists[botId]?.items ?? [] });
    try {
      const items = (await fileApi.list(orgId, botId)).map((f) => toBotFile(f, fileApi.contentUrl(orgId, f.id)));
      if (current()) setFileList(botId, { status: "ready", items });
    } catch (error) {
      if (current()) setFileList(botId, { status: "error", items: [], error: failure(error).error });
    }
  },

  /** Give a bot a file, at its name (the same name again replaces it). Any member. */
  async uploadFile(botId: string, file: File): Promise<ActionResult> {
    let saved: BotFile;
    if (isDemoMode()) {
      const result = saveMockFile(botId, file);
      if (!result.ok) return result;
      saved = result.file;
    } else {
      const orgId = state.org.id;
      try {
        const uploaded = await fileApi.upload(orgId, file, botId);
        saved = toBotFile(uploaded, fileApi.contentUrl(orgId, uploaded.id));
      } catch (error) {
        return failure(error);
      }
      if (state.org.id !== orgId) return { ok: true };
    }
    updateFileList(botId, (items) => withFile(items, saved));
    supersedeFileLoads(botId);
    return { ok: true };
  },

  /** Delete a file from the bot's folder and its storage (one in storage the org no longer uses only leaves the list). */
  async deleteFile(botId: string, fileId: string): Promise<ActionResult> {
    if (isDemoMode()) forgetDemoUrl(state.fileLists[botId]?.items.find((f) => f.id === fileId));
    else {
      try {
        await fileApi.remove(state.org.id, fileId);
      } catch (error) {
        return failure(error);
      }
    }
    updateFileList(botId, (items) => items.filter((f) => f.id !== fileId));
    supersedeFileLoads(botId);
    return { ok: true };
  },
};

/* ---------- A bot's browser (ADR 0017 §5) ----------
 * Watching a bot's browser and taking over (to sign in somewhere). It runs where the API runs, so
 * the demo has none to show. What a person types goes straight to the page and is never kept here.
 */

/** MOCK: the demo can't show a browser. */
const DEMO_BROWSER: BotBrowser = { available: false, open: false, width: 1280, height: 800, screenUrl: "" };

function sameBrowser(a: BotBrowser | undefined, b: BotBrowser) {
  return a !== undefined && (Object.keys(b) as (keyof BotBrowser)[]).every((k) => a[k] === b[k]) && Object.keys(a).length === Object.keys(b).length;
}

/** The browser as just seen. Polled every few seconds, so an unchanged one changes nothing (and re-renders nothing). */
function putBrowser(orgId: string, botId: string, seen: BotBrowser) {
  set((st) => {
    const load = st.browsers[botId];
    if (st.org.id !== orgId || (load?.status === "ready" && sameBrowser(load.current, seen))) return st;
    return { ...st, browsers: { ...st.browsers, [botId]: { status: "ready", current: seen } } };
  });
}

/** What you fill in to choose where browsers run. An empty `apiKey` keeps the saved one (the same provider). */
export type BrowserProviderInput =
  | { provider: "local" }
  | { provider: "steel" | "browserbase" | "kernel"; apiKey: string; projectId: string };

/** MOCK: "checks" the key like the API would (it starts a browser there), then switches. */
function saveMockBrowserProvider(input: BrowserProviderInput): ActionResult {
  const current = state.browserProvider.current;
  const localAvailable = current?.localAvailable ?? true;
  if (input.provider === "local") {
    if (!localAvailable) return { ok: false, error: "This server doesn't run browsers itself. Choose a cloud browser provider." };
    set((st) => ({ ...st, browserProvider: { status: "ready", current: { provider: "local", projectId: "", localAvailable } } }));
    return { ok: true };
  }
  const key = input.apiKey.trim();
  const keepsKey = !key && current?.provider === input.provider && current.keyHint !== undefined;
  if (!key && !keepsKey) return { ok: false, error: "Add the provider's API key." };
  if (key.startsWith("bad")) return { ok: false, error: "The provider refused the key: 401 Unauthorized." };
  const keyHint = keepsKey ? current?.keyHint : key.slice(-4);
  const projectId = input.provider === "browserbase" ? input.projectId.trim() : "";
  set((st) => ({
    ...st,
    browserProvider: { status: "ready", current: { provider: input.provider, projectId, localAvailable, checkedAt: now(), ...(keyHint ? { keyHint } : {}) } },
  }));
  return { ok: true };
}

const browserActions = {
  /** Where the org's bots' browsers run. The demo's is in its seed. */
  async loadBrowserProvider(): Promise<void> {
    if (isDemoMode()) return;
    const orgId = state.org.id;
    const loaded = await browserApi.provider(orgId).catch(() => null);
    set((st) => {
      if (st.org.id !== orgId) return st;
      return { ...st, browserProvider: loaded ? { status: "ready", current: toBrowserProvider(loaded) } : { ...st.browserProvider, status: "error" } };
    });
  },

  /** Choose Local or a cloud provider (owners and admins). The API starts and stops a browser there first, which can take a few seconds. */
  async saveBrowserProvider(input: BrowserProviderInput): Promise<ActionResult> {
    if (isDemoMode()) return saveMockBrowserProvider(input);
    const orgId = state.org.id;
    const body = input.provider === "local" ? input : {
      provider: input.provider,
      ...(input.apiKey.trim() ? { apiKey: input.apiKey.trim() } : {}),
      ...(input.provider === "browserbase" ? { projectId: input.projectId.trim() } : {}),
    };
    try {
      const saved = toBrowserProvider(await browserApi.chooseProvider(orgId, body));
      // Bots' browsers now run elsewhere: what's known about each one is out of date.
      set((st) => (st.org.id === orgId ? { ...st, browserProvider: { status: "ready", current: saved }, browsers: {} } : st));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Whether the bot's browser can be watched here, whether it's open, and on which page. */
  async loadBrowser(botId: string): Promise<void> {
    if (isDemoMode()) return putBrowser(state.org.id, botId, DEMO_BROWSER);
    const orgId = state.org.id;
    if (!state.browsers[botId]) set((st) => ({ ...st, browsers: { ...st.browsers, [botId]: { status: "loading" } } }));
    try {
      putBrowser(orgId, botId, toBotBrowser(await browserApi.state(orgId, botId), browserApi.screenUrl(orgId, botId)));
    } catch (error) {
      set((st) => {
        if (st.org.id !== orgId) return st;
        return { ...st, browsers: { ...st.browsers, [botId]: { ...st.browsers[botId], status: "error", error: failure(error).error } } };
      });
    }
  },

  /** Take over: a click, text, a key, a scroll, or an address to open (which starts the browser). `ok: false` says why the API refused. */
  async sendBrowserInput(botId: string, input: BrowserInput): Promise<ActionResult> {
    if (isDemoMode()) return { ok: false, error: "Not available in the demo." };
    const orgId = state.org.id;
    try {
      putBrowser(orgId, botId, toBotBrowser(await browserApi.input(orgId, botId, input), browserApi.screenUrl(orgId, botId)));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Close the bot's browser and forget every site it's signed in to. */
  async forgetSignIns(botId: string): Promise<ActionResult> {
    const orgId = state.org.id;
    if (!isDemoMode()) {
      try {
        await browserApi.forget(orgId, botId);
      } catch (error) {
        return failure(error);
      }
    }
    const before = state.browsers[botId]?.current;
    if (before) putBrowser(orgId, botId, { available: before.available, open: false, width: before.width, height: before.height, screenUrl: "" });
    return { ok: true };
  },
};

/* ---------- Routines ----------
 * On the API a routine runs on its schedule in its creator's DM with the bot; the API says it was
 * created there ("Created a routine" card). MOCK: saved here, and the bot confirms in its chat.
 */

/** The API's words for a routine whose bot was removed. */
const ROUTINE_BOT_REMOVED = "Its bot was removed.";

/** The browser's time zone: a routine's schedule is read in its creator's. */
const browserTimeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

function withRoutine(routines: Routine[], saved: Routine): Routine[] {
  return routines.some((r) => r.id === saved.id) ? routines.map((r) => (r.id === saved.id ? saved : r)) : [...routines, saved];
}

function toApiRoutine(input: NewRoutineInput) {
  return {
    botId: input.botId, name: input.name, instructions: input.description, enabled: input.enabled,
    cron: input.cron ?? "", timezone: input.timezone ?? browserTimeZone(),
  };
}

const routineActions = {
  /** Saves a new routine. On the API it needs `cron`; its creator's DM gets a "Created a routine" card. */
  async createRoutine(input: NewRoutineInput): Promise<{ ok: true; routineId: string } | { ok: false; error: string }> {
    if (isDemoMode()) {
      const routineId = `r_${id()}`;
      set((st) => ({ ...st, routines: [...st.routines, { ...input, id: routineId, source: "edit" }] }));
      const thread = state.threads.find((t) => t.kind === "dm" && t.botId === input.botId);
      if (thread) {
        pushBotMessage(thread.id, input.botId, [
          { type: "routine-created", routineId, name: input.name },
          { type: "text", text: `Got it. I'll run “${input.name}” ${input.schedule.charAt(0).toLowerCase()}${input.schedule.slice(1)}.` },
        ]);
      }
      return { ok: true, routineId };
    }
    const orgId = state.org.id;
    try {
      const saved = toRoutine(await routineApi.create(orgId, toApiRoutine(input)));
      set((st) => (st.org.id === orgId ? { ...st, routines: withRoutine(st.routines, saved) } : st));
      return { ok: true, routineId: saved.id };
    } catch (error) {
      return failure(error);
    }
  },

  /** Edit a routine (its creator, owners and admins). */
  async updateRoutine(routineId: string, input: NewRoutineInput): Promise<ActionResult> {
    if (isDemoMode()) {
      set((st) => ({ ...st, routines: st.routines.map((r) => (r.id === routineId ? { ...r, ...input } : r)) }));
      return { ok: true };
    }
    const orgId = state.org.id;
    try {
      const saved = toRoutine(await routineApi.update(orgId, routineId, toApiRoutine(input)));
      set((st) => (st.org.id === orgId ? { ...st, routines: withRoutine(st.routines, saved) } : st));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Switch a routine on or off. Shown at once; put back if the API says no. */
  async toggleRoutine(routineId: string): Promise<ActionResult> {
    const before = state.routines.find((r) => r.id === routineId);
    if (!before) return { ok: false, error: "This routine doesn't exist." };
    set((st) => ({ ...st, routines: st.routines.map((r) => (r.id === routineId ? { ...r, enabled: !before.enabled } : r)) }));
    if (isDemoMode()) return { ok: true };
    const orgId = state.org.id;
    try {
      const saved = toRoutine(await routineApi.update(orgId, routineId, { enabled: !before.enabled }));
      set((st) => (st.org.id === orgId ? { ...st, routines: withRoutine(st.routines, saved) } : st));
      return { ok: true };
    } catch (error) {
      set((st) => (st.org.id === orgId ? { ...st, routines: withRoutine(st.routines, before) } : st));
      return failure(error);
    }
  },

  /** Run it once now, without moving its schedule. On the API the run happens in its creator's DM. */
  async runRoutineNow(routineId: string): Promise<ActionResult> {
    if (isDemoMode()) {
      set((st) => ({ ...st, routines: st.routines.map((r) => (r.id === routineId ? { ...r, lastRunAt: now(), lastOutcome: "running" } : r)) }));
      return { ok: true };
    }
    const orgId = state.org.id;
    try {
      await routineApi.runNow(orgId, routineId);
    } catch (error) {
      return failure(error);
    }
    await loadRoutines(orgId);
    return { ok: true };
  },

  /** Remove a routine for good (its creator, owners and admins). */
  async deleteRoutine(routineId: string): Promise<ActionResult> {
    try {
      if (!isDemoMode()) await routineApi.remove(state.org.id, routineId);
    } catch (error) {
      return failure(error);
    }
    set((st) => ({ ...st, routines: st.routines.filter((r) => r.id !== routineId) }));
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
  ...fileActions,
  ...browserActions,

  /**
   * Sends your message. Bots reply in a moment (ADR 0009): in a DM its bot, or the other bots you
   * @mention as guests; in a group the bots you @mention, or else its lead.
   */
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

    // MOCK: the same rules as the API (lib/mention-routing.ts mirrors services/mention_routing.py).
    const thread = s.threads.find((t) => t.id === threadId);
    if (!thread) return;
    const routing = routeMessage(mockChatBots(s, thread), text, { orgBots: s.bots, hopLimit: HOP_LIMIT });
    queueMockReplies(threadId, routing.replies, text);
  },

  /** Marks the question answered. On the API the answer is also sent as your message, so the bot gets it. */
  answerQuestion(messageId: string, answer: string) {
    const threadId = state.messages.find((m) => m.id === messageId)?.threadId;
    set((st) => ({
      ...st,
      messages: st.messages.map((m) =>
        m.id === messageId
          ? { ...m, parts: m.parts.map((p) => (p.type === "question" ? { ...p, answered: answer } : p)) }
          : m,
      ),
    }));
    if (threadId && !isDemoMode()) actions.sendMessage(threadId, answer);
  },

  /** You've seen this chat: its count drops to 0 here and, on the API, for your other devices too. */
  markRead(threadId: string) {
    readAt.set(threadId, tick());
    set((st) => ({ ...st, threads: st.threads.map((t) => (t.id === threadId && t.unread !== 0 ? { ...t, unread: 0 } : t)) }));
    if (!isDemoMode() && state.authStatus === "signed-in") void threadApi.markRead(state.org.id, threadId).catch(() => {});
  },

  updateBot(botId: string, patch: Partial<Bot>) {
    set((st) => ({ ...st, bots: st.bots.map((b) => (b.id === botId ? { ...b, ...patch } : b)) }));
  },

  ...routineActions,

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
    try {
      return await openNewBot(orgId, toBot(await botApi.create(orgId, toApiBot(input))));
    } catch (error) {
      return failure(error);
    }
  },

  /** The marketplace again, after it failed to load (API). The demo has its own. */
  async loadTemplates(): Promise<void> {
    if (!isDemoMode() && state.authStatus === "signed-in") await loadTemplates();
  },

  /**
   * Hire a ready-made bot from the marketplace and open its DM. On the API, the API makes it from
   * its own catalogue: the template's instructions and Tools, the instance's default model, and the
   * template's security level or the org's default, whichever is stricter. The demo does the same.
   */
  async createBotFromTemplate(templateId: string): Promise<ActionResult & { threadId?: string }> {
    const t = state.templates.items.find((x) => x.id === templateId);
    if (!t) return { ok: false, error: "That bot isn't in the marketplace any more." };
    if (isDemoMode()) {
      return actions.createBot({
        name: t.name, role: t.role, description: t.description, avatarColor: t.avatarColor, instructions: t.instructions,
        modelId: "m_claude", securityLevel: strictestLevel(t.securityLevel, state.org.defaultSecurityLevel), computerMode: "own",
        monthlyBudgetUsd: HIRED_BUDGET_USD,
      });
    }
    const orgId = state.org.id;
    try {
      return await openNewBot(orgId, toBot(await templateApi.hire(orgId, t.id)));
    } catch (error) {
      return failure(error);
    }
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
      // Its DM is gone on the API too: a chat list already on its way mustn't bring it back.
      st.threads.forEach((t) => !kept.has(t.id) && removedAt.set(t.id, tick()));
      return {
        ...st,
        bots: st.bots.filter((b) => b.id !== botId),
        threads,
        messages: st.messages.filter((m) => kept.has(m.threadId)),
        runs: st.runs.filter((r) => kept.has(r.threadId) && r.botId !== botId),
        approvals: st.approvals.filter((a) => a.botId !== botId),
        // On the API its routines stay, switched off, saying why (the demo just drops them).
        routines: isDemoMode()
          ? st.routines.filter((r) => r.botId !== botId)
          : st.routines.map((r) => (r.botId === botId ? { ...r, botId: "", enabled: false, nextRunAt: undefined, disabledReason: ROUTINE_BOT_REMOVED } : r)),
      };
    });
    return { ok: true };
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

  /** The plugins the server loaded, for Connect apps. The demo has none to load. */
  async loadPlugins(): Promise<void> {
    if (isDemoMode()) return;
    const orgId = state.org.id;
    const items = await pluginApi.list(orgId).catch(() => null);
    set((st) => {
      if (st.org.id !== orgId) return st; // switched org while loading
      return { ...st, plugins: items ? { status: "ready", items } : { ...st.plugins, status: "error" } };
    });
  },

  disconnectApp(connectionId: string) {
    set((st) => ({ ...st, connections: st.connections.filter((c) => c.id !== connectionId) }));
  },

  /** Connect apps on the API: the server's connectors and the accounts you may see, together. */
  async loadConnections(): Promise<void> {
    if (isDemoMode()) return;
    const orgId = state.org.id;
    const [connectors, accounts] = await Promise.all([
      connectionApi.connectors(orgId).catch(() => null),
      connectionApi.list(orgId).catch(() => null),
    ]);
    set((st) => {
      if (st.org.id !== orgId) return st; // switched org while loading
      return {
        ...st,
        serverConnectors: connectors ? { status: "ready", items: connectors } : { ...st.serverConnectors, status: "error" },
        accounts: accounts ? { status: "ready", items: accounts.map(toAccountConnection) } : { ...st.accounts, status: "error" },
      };
    });
  },

  /**
   * Sign in with the provider (OAuth): the API gives the provider's page, and the whole tab goes
   * there. It comes back to /apps/callback, which then goes back to `returnTo`: the page you
   * pressed Connect on, unless said otherwise. Reconnecting is the same, with the same owner.
   */
  async startOAuth(connectorId: string, owner: ConnectionOwner, access?: string, returnTo = browser.here()): Promise<ActionResult> {
    if (isDemoMode()) return { ok: false, error: "Signing in to apps works once botdesk is connected to its API." };
    try {
      const { authorizeUrl } = await connectionApi.startOAuth(state.org.id, { connectorId, ...ownerFields(owner), ...(access ? { access } : {}) });
      rememberOAuthReturn(returnTo);
      browser.leaveFor(authorizeUrl);
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Connect an account with an API key. The key is sent once and never kept here. */
  async connectApiKey(connectorId: string, owner: ConnectionOwner, accountLabel: string, apiKey: string): Promise<ActionResult> {
    if (isDemoMode()) return { ok: false, error: "Connecting with a key works once botdesk is connected to its API." };
    const orgId = state.org.id;
    try {
      const saved = toAccountConnection(await connectionApi.connectApiKey(orgId, { connectorId, ...ownerFields(owner), accountLabel, apiKey }));
      set((st) => (st.org.id !== orgId ? st : { ...st, accounts: { ...st.accounts, items: [...st.accounts.items.filter((c) => c.id !== saved.id), saved] } }));
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Disconnect an account: the API forgets its credential and revokes it at the provider. */
  async disconnectConnection(connectionId: string): Promise<ActionResult> {
    if (!isDemoMode()) {
      try {
        await connectionApi.disconnect(state.org.id, connectionId);
      } catch (error) {
        return failure(error);
      }
    }
    const revoked = (c: AccountConnection): AccountConnection => (c.id === connectionId ? { ...c, status: "revoked" } : c);
    set((st) => ({
      ...st,
      accounts: { ...st.accounts, items: st.accounts.items.map(revoked) },
      // A disconnected account leaves every bot that used it.
      botTools: Object.fromEntries(
        Object.entries(st.botTools).map(([botId, tools]) => [
          botId,
          { ...tools, plugins: tools.plugins.map((p) => (p.connectionId === connectionId ? { ...p, connectionId: null } : p)) },
        ]),
      ),
    }));
    return { ok: true };
  },

  /** Connect apps: the organization's MCP servers. The demo has none (it can't add any). */
  async loadMcpServers(): Promise<void> {
    if (isDemoMode()) return;
    const orgId = state.org.id;
    const servers = await mcpApi.list(orgId).catch(() => null);
    set((st) =>
      st.org.id !== orgId ? st
      : { ...st, mcpServers: servers ? { status: "ready", items: servers.map(toMcpServer) } : { ...st.mcpServers, status: "error" } },
    );
  },

  /**
   * Owners and admins: add an MCP server. The API connects and lists its tools before saving;
   * none is offered to bots until they're reviewed (`serverId` → /apps/mcp/[serverId]). A server
   * that wants a sign-in sends the tab to its sign-in page (`signingIn`), back on /apps/callback.
   */
  async addMcpServer(input: McpServerInput): Promise<{ ok: true; serverId: string; signingIn: boolean } | { ok: false; error: string }> {
    if (isDemoMode()) return { ok: false, error: "Adding MCP servers works once botdesk is connected to its API." };
    const orgId = state.org.id;
    try {
      const added = await mcpApi.add(orgId, input);
      const saved = toMcpServer(added);
      // Bots' Tools tabs now have one more plugin: they load again when next opened.
      set((st) => (st.org.id !== orgId ? st : { ...st, mcpServers: { status: "ready", items: [...st.mcpServers.items, saved] }, botTools: {} }));
      if (added.authorizeUrl) browser.leaveFor(added.authorizeUrl);
      return { ok: true, serverId: saved.id, signingIn: Boolean(added.authorizeUrl) };
    } catch (error) {
      return failure(error);
    }
  },

  /** Owners and admins: list the server's tools again. Changed and new ones wait for the review. */
  async refreshMcpServer(serverId: string): Promise<ActionResult> {
    if (isDemoMode()) return { ok: false, error: "MCP servers work once botdesk is connected to its API." };
    const orgId = state.org.id;
    try {
      const saved = toMcpServer(await mcpApi.refresh(orgId, serverId));
      set((st) =>
        st.org.id !== orgId ? st
        : { ...st, mcpServers: { ...st.mcpServers, items: st.mcpServers.items.map((s) => (s.id === serverId ? saved : s)) }, botTools: {} },
      );
      return saved.status === "unreachable" ? { ok: false, error: saved.statusReason ?? "Couldn't reach the server." } : { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Owners and admins: approve tools as they are now, on or off for bots, at these risks (Review tools). */
  async reviewMcpTools(serverId: string, toolsHash: string, tools: McpToolChoice[]): Promise<ActionResult> {
    if (isDemoMode()) return { ok: false, error: "MCP servers work once botdesk is connected to its API." };
    const orgId = state.org.id;
    try {
      const saved = toMcpServer(await mcpApi.reviewTools(orgId, serverId, { toolsHash, tools }));
      set((st) =>
        st.org.id !== orgId ? st
        : { ...st, mcpServers: { ...st.mcpServers, items: st.mcpServers.items.map((s) => (s.id === serverId ? saved : s)) }, botTools: {} },
      );
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Owners and admins: sign in to an OAuth MCP server again (Reconnect). The tab leaves for its sign-in page. */
  async signInMcpServer(serverId: string): Promise<ActionResult> {
    if (isDemoMode()) return { ok: false, error: "MCP servers work once botdesk is connected to its API." };
    try {
      const { authorizeUrl } = await mcpApi.signIn(state.org.id, serverId);
      browser.leaveFor(authorizeUrl);
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Owners and admins: remove the server; every bot loses its tools. */
  async removeMcpServer(serverId: string): Promise<ActionResult> {
    if (isDemoMode()) return { ok: false, error: "MCP servers work once botdesk is connected to its API." };
    const orgId = state.org.id;
    try {
      await mcpApi.remove(orgId, serverId);
    } catch (error) {
      return failure(error);
    }
    set((st) => (st.org.id !== orgId ? st : { ...st, mcpServers: { ...st.mcpServers, items: st.mcpServers.items.filter((s) => s.id !== serverId) }, botTools: {} }));
    return { ok: true };
  },

  /** A bot's Tools tab. MOCK in the demo: every bot starts with the demo tools on. */
  async loadBotTools(botId: string): Promise<void> {
    if (isDemoMode()) {
      if (!state.botTools[botId]) setBotTools(botId, { status: "ready", plugins: mock.botToolPlugins });
      if (state.accounts.items.length === 0) set((st) => ({ ...st, accounts: { status: "ready", items: mock.accountConnections } }));
      return;
    }
    const orgId = state.org.id;
    if (!state.botTools[botId]) setBotTools(botId, { status: "loading", plugins: [] });
    const [tools, accounts] = await Promise.all([
      connectionApi.botTools(orgId, botId).catch(() => null),
      connectionApi.list(orgId).catch(() => null),
    ]);
    if (state.org.id !== orgId) return;
    setBotTools(botId, tools ? { status: "ready", plugins: tools.plugins } : { status: "error", plugins: state.botTools[botId]?.plugins ?? [] });
    if (accounts) set((st) => ({ ...st, accounts: { status: "ready", items: accounts.map(toAccountConnection) } }));
  },

  /** Turn plugins on or off for a bot, or change the account one works through. */
  async setBotTools(botId: string, changes: BotToolChange[]): Promise<ActionResult> {
    if (isDemoMode()) {
      const current = state.botTools[botId]?.plugins ?? mock.botToolPlugins;
      const plugins = current.map((p) => {
        const change = changes.find((c) => c.pluginId === p.pluginId);
        return change ? { ...p, enabled: change.enabled, connectionId: change.connectionId } : p;
      });
      setBotTools(botId, { status: "ready", plugins });
      return { ok: true };
    }
    const orgId = state.org.id;
    try {
      const saved = await connectionApi.setBotTools(orgId, botId, changes);
      if (state.org.id === orgId) setBotTools(botId, { status: "ready", plugins: saved.plugins });
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Switch a plugin's trigger on (its events come to your DM with the bot) or off. API mode only. */
  async setBotTrigger(botId: string, pluginId: string, trigger: string, enabled: boolean): Promise<ActionResult> {
    if (isDemoMode()) return { ok: false, error: "Triggers work once botdesk is connected to its API." };
    const orgId = state.org.id;
    try {
      const saved = await connectionApi.setBotTrigger(orgId, botId, pluginId, trigger, enabled);
      if (state.org.id === orgId) setBotTools(botId, { status: "ready", plugins: saved.plugins });
      return { ok: true };
    } catch (error) {
      return failure(error);
    }
  },

  /** Back to the original mock data. Also cancels bot replies still in progress, so none land afterwards. */
  reset() {
    cancelMockTimers();
    closeChatStreams();
    restoring = null;
    signUpMode = { mode: null, loading: null };
    set(() => seed());
  },
};

function setBotTools(botId: string, tools: BotTools) {
  set((st) => ({ ...st, botTools: { ...st.botTools, [botId]: tools } }));
}

/** The API's owner fields for a connection: `botId` only for a bot's own account. */
function ownerFields(owner: ConnectionOwner): { ownerKind: ConnectionOwner["kind"]; botId?: string } {
  return owner.kind === "bot" ? { ownerKind: "bot", botId: owner.botId } : { ownerKind: owner.kind };
}

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

/** What a bot hired from the marketplace may spend a month (the API's `HIRED_BUDGET_USD`). */
const HIRED_BUDGET_USD = 20;

/** A bot the API just made joins the team, and its DM opens (every bot has one). */
async function openNewBot(orgId: string, bot: Bot): Promise<ActionResult & { threadId?: string }> {
  set((st) => (st.org.id !== orgId ? st : { ...st, bots: [...st.bots, bot] }));
  try {
    const dm = toThread(await threadApi.openDm(orgId, bot.id));
    set((st) => (st.org.id !== orgId ? st : { ...st, threads: [...st.threads.filter((t) => t.id !== dm.id), dm] }));
    return { ok: true, threadId: dm.id };
  } catch {
    return { ok: false, error: `${bot.name} is on your team, but their chat didn't open. Reload the page to try again.` };
  }
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
  mockQueues.clear();
  mockDemoRuns.clear();
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

/**
 * MOCK ONLY: who may be @mentioned by a bot in this chat. A group: its bots and lead. A DM: its
 * bot, plus every bot that has replied there (guests), as the API counts bots that had a run.
 */
function mockChatBots(s: State, thread: Thread): ChatBots {
  if (thread.kind === "group") {
    return { kind: "group", bots: thread.participants.filter((p) => p.type === "bot").map((p) => p.id), defaultBot: thread.leadBotId };
  }
  const guests = s.messages.filter((m) => m.threadId === thread.id && m.author.type === "bot").map((m) => m.author.id);
  return { kind: "dm", bots: [...new Set([...(thread.botId ? [thread.botId] : []), ...guests])], defaultBot: thread.botId };
}

/** MOCK ONLY: replies waiting their turn, per chat (one bot replies at a time, as on the API). */
const mockQueues = new Map<string, { reply: BotReply; trigger: string }[]>();

function queueMockReplies(threadId: string, replies: BotReply[], trigger: string) {
  const queue = mockQueues.get(threadId) ?? [];
  const idle = queue.length === 0;
  queue.push(...replies.map((reply) => ({ reply, trigger })));
  mockQueues.set(threadId, queue);
  if (idle && queue.length > 0) fakeBotReply(threadId, queue[0].reply, queue[0].trigger);
}

/**
 * MOCK ONLY: a reply finished. Bots it @mentions get their turn one hop on (past the hop limit the
 * chat says the chain stopped), then the next queued reply starts.
 */
function finishMockReply(threadId: string, reply: BotReply, text: string) {
  const thread = state.threads.find((t) => t.id === threadId);
  const queue = mockQueues.get(threadId) ?? [];
  queue.shift();
  if (thread) {
    const routing = routeMessage(mockChatBots(state, thread), text, { orgBots: state.bots, hopLimit: HOP_LIMIT, byBot: reply });
    queue.push(...routing.replies.map((next) => ({ reply: next, trigger: text })));
    if (routing.chainStopped) pushSystemNotice(threadId, chainStoppedText(HOP_LIMIT));
  }
  if (queue.length === 0) return void mockQueues.delete(threadId);
  fakeBotReply(threadId, queue[0].reply, queue[0].trigger);
}

function pushSystemNotice(threadId: string, text: string) {
  const msg: Message = { id: id(), threadId, author: { type: "system", id: "system" }, parts: [{ type: "text", text }], createdAt: now() };
  set((st) => ({ ...st, messages: [...st.messages, msg] }));
}

/**
 * MOCK ONLY: what a fake bot says. It repeats the request (with its @s dropped, so quoting never
 * mentions anyone). Asked to "relay", it passes the work to the next bot in the chat, so the demo
 * shows bots handing over to each other until the hop limit stops the chain.
 */
function mockReplyText(threadId: string, botId: string, trigger: string): string {
  const quote = trigger.replaceAll("@", "").slice(0, 60) + (trigger.length > 60 ? "…" : "");
  const text = `Got it. I'll take care of “${quote}” and report back here. (This is mock data; real bots arrive with the API.)`;
  const thread = state.threads.find((t) => t.id === threadId);
  if (!thread || !/\brelay\b/i.test(trigger)) return text;
  const bots = mockChatBots(state, thread).bots;
  const next = bots[(bots.indexOf(botId) + 1) % bots.length];
  const handle = next && next !== botId ? state.bots.find((b) => b.id === next)?.handle : undefined;
  return handle ? `${text} Relay: passing it on to @${handle}.` : text;
}

/** MOCK ONLY: simulates a bot streaming a reply. Real replies arrive over realtime. */
function fakeBotReply(threadId: string, reply: BotReply, userText: string) {
  const bot = state.bots.find((b) => b.id === reply.botId);
  if (!bot) return finishMockReply(threadId, reply, "");
  if (bot.id === chiefDemo.chiefId && chiefDemo.trigger.test(userText)) return playChiefDemo(threadId, reply);
  const full = mockReplyText(threadId, bot.id, userText);
  streamMockReply(threadId, bot, full, () => finishMockReply(threadId, reply, full));
}

const setBotStatus = (botId: string, status: Bot["status"], statusText: string) =>
  set((st) => ({ ...st, bots: st.bots.map((b) => (b.id === botId ? { ...b, status, statusText } : b)) }));

/**
 * MOCK ONLY: a bot thinks for a moment, then writes `text` two words at a time. `done` gets the
 * reply's id. `isStopped` ends it early (a person pressed Stop): the words so far stay.
 */
function streamMockReply(threadId: string, bot: Bot, text: string, done: (messageId: string) => void, isStopped = () => false) {
  setBotStatus(bot.id, "working", "Thinking…");
  const words = text.split(" ");
  let i = 0;
  const reasoning = `Reading the request, checking ${bot.name}'s tools and memory, planning steps.`;

  later(() => {
    if (isStopped()) return setBotStatus(bot.id, "idle", "Stopped");
    const msgId = pushBotMessage(threadId, bot.id, [{ type: "reasoning", text: reasoning, durationSec: 2 }, { type: "text", text: "" }], "streaming");
    every((stop) => {
      const stopped = isStopped();
      i += 2;
      const finished = stopped || i >= words.length;
      const shown = words.slice(0, stopped ? i - 2 : i).join(" ");
      set((st) => ({
        ...st,
        messages: st.messages.map((m) =>
          m.id === msgId
            ? { ...m, status: finished ? "complete" : "streaming", parts: m.parts.map((p) => (p.type === "text" ? { ...p, text: shown } : p)) }
            : m,
        ),
      }));
      if (!finished) return;
      stop();
      // The reply started empty, so the chat list shows its words only now.
      if (shown) set((st) => ({ ...st, threads: st.threads.map((t) => (t.id === threadId ? { ...t, lastMessagePreview: shown } : t)) }));
      setBotStatus(bot.id, "idle", stopped ? "Stopped" : "Just replied");
      if (!stopped) done(msgId);
    }, 60);
  }, 600);
}

/* ---------- MOCK ONLY: the Chief demo (handoffs, ADR 0014) ----------
 * Chief hands two Tasks to teammates and pauses (`waiting_handoff`). Each teammate works and
 * replies in turn, and its card moves from queued to working to done. Then Chief resumes and
 * writes one combined answer as a new message. It's the API's flow, played on timers.
 */

/** Demo runs still going, by run id: what Stop needs to wind one down. */
const mockDemoRuns = new Map<string, { threadId: string; reply: BotReply; taskIds: string[] }>();

function setMockRun(run: ActiveRun | null, runId: string) {
  set((st) => withRunStatus({ ...st, runs: [...st.runs.filter((r) => r.id !== runId), ...(run ? [run] : [])] }));
}

function changeMockTask(change: TaskChange) {
  set((st) => ({ ...st, messages: withTaskChangeIn(st.messages, change), taskChanges: { ...st.taskChanges, [change.taskId]: change } }));
}

function playChiefDemo(threadId: string, reply: BotReply) {
  const chief = state.bots.find((b) => b.id === reply.botId)!;
  const runId = `mock-run-${id()}`;
  const taskIds = chiefDemo.tasks.map(() => `mock-task-${id()}`);
  const isStopped = () => !mockDemoRuns.has(runId);
  mockDemoRuns.set(runId, { threadId, reply, taskIds });
  setMockRun({ id: runId, threadId, botId: chief.id }, runId);

  later(() => {
    if (isStopped()) return;
    pushBotMessage(threadId, chief.id, [
      { type: "text", text: chiefDemo.opener },
      ...chiefDemo.tasks.map((t, i) => ({ type: "handoff" as const, taskId: taskIds[i], fromBotId: chief.id, toBotId: t.toBotId, task: t.task, status: "queued" as const })),
    ]);
    setMockRun({ id: runId, threadId, botId: chief.id, status: "waiting_handoff", taskIds }, runId);
    later(() => workOnTask(0), 700);
  }, 600);

  // Teammates take their turns one after another in this chat, as on the API.
  function workOnTask(index: number) {
    if (isStopped()) return;
    const task = chiefDemo.tasks[index];
    const bot = state.bots.find((b) => b.id === task?.toBotId);
    if (!task || !bot) return resume();
    changeMockTask({ taskId: taskIds[index], status: "working" });
    streamMockReply(threadId, bot, task.reply, (messageId) => {
      changeMockTask({ taskId: taskIds[index], status: "done", resultMessageId: messageId, resultPreview: taskPreview(task.reply) });
      later(() => workOnTask(index + 1), 500);
    }, isStopped);
  }

  function resume() {
    setMockRun({ id: runId, threadId, botId: chief.id, status: "running" }, runId);
    streamMockReply(threadId, chief, chiefDemo.finalAnswer, () => {
      mockDemoRuns.delete(runId);
      setMockRun(null, runId);
      finishMockReply(threadId, reply, chiefDemo.finalAnswer);
    }, isStopped);
  }
}

/** MOCK ONLY: Stop on a demo run. Its open Tasks are cancelled, as the API does when a parent ends first. */
function stopMockRun(runId: string) {
  const run = mockDemoRuns.get(runId);
  if (!run) return;
  mockDemoRuns.delete(runId);
  const chief = state.bots.find((b) => b.id === run.reply.botId);
  for (const taskId of run.taskIds) {
    if (!isTaskOpen(state.taskChanges[taskId]?.status ?? "queued")) continue;
    changeMockTask({ taskId, status: "cancelled", error: `Cancelled: ${chief?.name ?? "the bot"} stopped before it finished.` });
  }
  setMockRun(null, runId);
  finishMockReply(run.threadId, run.reply, "");
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

/*
 * The sign-up mode, asked once per page load (it only changes when the server restarts). Kept
 * apart from `state` since it belongs to the server, not to who is signed in. If the API can't
 * be reached it reads as open, so the form shows and sign-up itself says what's wrong.
 */
let signUpMode: { mode: SignUpMode | null; loading: Promise<void> | null } = { mode: null, loading: null };
const signUpModeListeners = new Set<() => void>();

function subscribeSignUpMode(listener: () => void) {
  signUpModeListeners.add(listener);
  if (!isDemoMode() && !signUpMode.loading) {
    const current = signUpMode;
    current.loading = authApi.options().then(
      ({ signUpMode: mode }) => void (current.mode = mode),
      () => void (current.mode = "open"),
    ).then(() => signUpModeListeners.forEach((notify) => notify()));
  }
  return () => void signUpModeListeners.delete(listener);
}

/** Open, invite-only or closed; null until the API answers (and on the server). Always open in the demo. */
export function useSignUpMode(): SignUpMode | null {
  return useSyncExternalStore(
    subscribeSignUpMode,
    () => (isDemoMode() ? "open" : signUpMode.mode),
    () => null,
  );
}
/**
 * True when screens show the demo (no API, or a guest). Screens the API doesn't cover yet use it
 * to say so instead of pretending to work.
 */
export const useIsDemo = () => useStore(useCallback((s: State) => isDemo(s), []));
export const useCurrentUser = () => useStore(useCallback((s: State) => s.users.find((u) => u.id === s.currentUserId)!, []));
export const useUser = (id?: string) => useStore(useCallback((s: State) => s.users.find((u) => u.id === id), [id]));
export const useBot = (id?: string) => useStore(useCallback((s: State) => s.bots.find((b) => b.id === id), [id]));
export const useModel = (id?: string) => useStore(useCallback((s: State) => s.models.find((m) => m.id === id), [id]));
export const useThread = (id?: string) => useStore(useCallback((s: State) => s.threads.find((t) => t.id === id), [id]));

/** Whether you may change this group's lead: its creator, and the organization's owners and admins. */
export const useCanChangeLead = (thread: Thread) =>
  useStore(
    useCallback(
      (s: State) => {
        const me = s.users.find((u) => u.id === s.currentUserId);
        return thread.kind === "group" && (thread.createdBy === s.currentUserId || me?.role === "owner" || me?.role === "admin");
      },
      [thread.kind, thread.createdBy],
    ),
  );

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
/** Runs in this chat paused until the Tasks they handed off have ended (ADR 0014). */
export const useRunsWaitingOnTasks = (threadId: string) =>
  useStore(useCallback((s: State) => s.runs.filter((r) => r.threadId === threadId && r.status === "waiting_handoff"), [threadId]));

/**
 * The teammates a waiting run waits for: the owners of its open Tasks, or of all its Tasks once
 * none is open (it's about to resume). Its Tasks are the ones the stream named; a chat opened
 * mid-wait doesn't know them, so it reads the open cards in the run's bot's messages.
 */
export const useWaitedOnBots = (run: ActiveRun) => {
  const { threadId, botId, taskIds } = run;
  const key = taskIds?.join(" ");
  return useStore(
    useCallback(
      (s: State) => {
        const ids = key?.split(" ");
        const cards = s.messages
          .filter((m) => m.threadId === threadId && (ids || m.author.id === botId))
          .flatMap((m) => m.parts.filter((p) => p.type === "handoff"))
          .filter((p) => (ids ? ids.includes(p.taskId) : isTaskOpen(p.status)));
        const open = cards.filter((p) => isTaskOpen(p.status));
        return [...new Set((open.length > 0 ? open : cards).map((p) => p.toBotId))];
      },
      [threadId, botId, key],
    ),
  );
};

export const usePendingApprovalCount = () => useStore(useCallback((s: State) => selectPendingApprovals(s).length, []));

export const useBotRoutines = (botId?: string) =>
  useStore(useCallback((s: State) => s.routines.filter((r) => r.botId === botId), [botId]));

/** A bot's memories as last loaded with `actions.loadMemories`; undefined until then. */
export const useMemoryList = (botId?: string) =>
  useStore(useCallback((s: State) => (botId ? s.memoryLists[botId] : undefined), [botId]));

/** Whether bots can remember here (null while the API is asked). */
export const useMemoryStatus = () => useStore(useCallback((s: State) => s.memoryStatus, []));
/** Where the org keeps bots' files (Settings → Computers). */
export const useFileStorage = () => useStore(useCallback((s: State) => s.storage, []));
/** Where the org's bots' browsers run (Settings → Computers). */
export const useBrowserProvider = () => useStore(useCallback((s: State) => s.browserProvider, []));
/** A bot's browser as last seen; undefined until `actions.loadBrowser` has started. */
export const useBotBrowser = (botId?: string) =>
  useStore(useCallback((s: State) => (botId ? s.browsers[botId] : undefined), [botId]));
/** A bot's files as last loaded; undefined until `actions.loadFiles` has started. */
export const useFileList = (botId?: string) =>
  useStore(useCallback((s: State) => (botId ? s.fileLists[botId] : undefined), [botId]));

/* Whole-collection hooks for the app pages (marketplace, settings, approvals…). */
export const useBots = () => useStore(useCallback((s: State) => s.bots, []));
export const useBotsLoading = () => useStore(useCallback((s: State) => s.botsLoading, []));
export const useUsers = () => useStore(useCallback((s: State) => s.users, []));
export const useInvitations = () => useStore(useCallback((s: State) => s.invitations, []));
export const useModels = () => useStore(useCallback((s: State) => s.models, []));
export const useModelProviders = () => useStore(useCallback((s: State) => s.modelProviders, []));
/** My keys in the current org; null until loaded (`actions.loadMyKeys`). */
export const useMyKeys = () => useStore(useCallback((s: State) => s.myKeys, []));
/** Connected providers whose models couldn't be listed just now. */
export const useModelProblems = () => useStore(useCallback((s: State) => s.modelProblems, []));
/** API only: true while providers and models are on their way. */
export const useModelsLoading = () => useStore(useCallback((s: State) => s.modelsLoading, []));
export const useTemplates = () => useStore(useCallback((s: State) => s.templates.items, []));
/** The marketplace with whether it has loaded (API), for a loading or error state. */
export const useTemplateList = () => useStore(useCallback((s: State) => s.templates, []));
export const useRoutines = () => useStore(useCallback((s: State) => s.routines, []));
export const useRoutine = (routineId?: string) =>
  useStore(useCallback((s: State) => s.routines.find((r) => r.id === routineId), [routineId]));
/** API only: true while the org's routines are on their way. */
export const useRoutinesLoading = () => useStore(useCallback((s: State) => s.routinesLoading, []));
export const useUsage = () => useStore(useCallback((s: State) => s.usage, []));
export const useUsageLoading = () => useStore(useCallback((s: State) => s.usageLoading, []));
export const useConnectors = () => useStore(useCallback((s: State) => s.connectors, []));
export const usePlugins = () => useStore(useCallback((s: State) => s.plugins, []));
export const useConnections = () => useStore(useCallback((s: State) => s.connections, []));
/** Connect apps on the API: the server's connectors, as last loaded with `actions.loadConnections`. */
export const useServerConnectors = () => useStore(useCallback((s: State) => s.serverConnectors, []));
/** Connect apps: the organization's MCP servers, as last loaded with `actions.loadMcpServers`. */
export const useMcpServers = () => useStore(useCallback((s: State) => s.mcpServers, []));
/** Accounts connected to connectors that you may see (yours, the bots', the organization's). */
export const useAccountConnections = () => useStore(useCallback((s: State) => s.accounts, []));
/** A bot's Tools tab, as last loaded with `actions.loadBotTools`; undefined until then. */
export const useBotTools = (botId: string) => useStore(useCallback((s: State) => s.botTools[botId], [botId]));

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
