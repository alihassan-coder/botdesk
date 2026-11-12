"use client";

/**
 * Client-side data store for the UI.
 *
 * Today it is seeded from mock fixtures and mutations happen in memory, with fake bot
 * replies, so every screen is clickable. When apps/api exists, replace the `seed()` and
 * the action bodies with calls to `packages/sdk` (and realtime events); the hooks and
 * screens stay the same.
 */
import { useCallback, useRef, useSyncExternalStore } from "react";
import { makeHandle } from "@/lib/handle";
import { parseMentions } from "@/lib/mentions";
import * as mock from "./mock/fixtures";
import type { Approval, ApprovalStatus, Bot, Message, Org, Participant, ProviderCredential, Routine, Thread, User } from "./types";

/** What you fill in to create a bot; the rest (id, handle, status…) is filled in for you. */
export type NewBotInput = Pick<
  Bot,
  "name" | "role" | "description" | "avatarColor" | "modelId" | "securityLevel" | "computerMode" | "instructions" | "monthlyBudgetUsd"
>;

/** What you fill in to create a routine. */
export type NewRoutineInput = Pick<Routine, "botId" | "name" | "description" | "schedule" | "steps" | "enabled">;

/** "unknown" until the browser has checked for a saved session (first render, server). */
export type AuthStatus = "unknown" | "signed-in" | "signed-out";

type AuthResult = { ok: true } | { ok: false; error: string };

interface State {
  org: typeof mock.org;
  users: typeof mock.users;
  currentUserId: string;
  authStatus: AuthStatus;
  /** MOCK: email → password. Replaced by Better Auth on the API. */
  passwords: Record<string, string>;
  bots: Bot[];
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
    users: mock.users,
    currentUserId: mock.currentUserId,
    authStatus: "unknown",
    passwords: mock.mockPasswords,
    bots: mock.bots,
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


/* ---------- Session (MOCK) ----------
 * The signed-in user is remembered in this browser. The real app uses Better Auth
 * cookies set by apps/api; screens won't change, only these functions.
 */
const SESSION_KEY = "botdesk.session";

function saveSession(user: User | null) {
  try {
    if (user) localStorage.setItem(SESSION_KEY, JSON.stringify({ user }));
    else localStorage.removeItem(SESSION_KEY);
  } catch {}
}

function startSession(user: User) {
  set((st) => ({
    ...st,
    users: st.users.some((u) => u.id === user.id) ? st.users : [...st.users, user],
    currentUserId: user.id,
    authStatus: "signed-in",
  }));
  saveSession(user);
}

const authActions = {
  /** Called once when the app loads: are we already signed in on this device? */
  restoreSession() {
    try {
      const saved = JSON.parse(localStorage.getItem(SESSION_KEY) ?? "null") as { user?: User; userId?: string } | null;
      const user = saved?.user ?? state.users.find((u) => u.id === saved?.userId);
      if (user) return startSession(user);
    } catch {}
    set((st) => ({ ...st, authStatus: "signed-out" }));
  },

  signIn(email: string, password: string): AuthResult {
    const user = state.users.find((u) => u.email.toLowerCase() === email.trim().toLowerCase());
    if (!user || state.passwords[user.email] !== password) return { ok: false, error: "That email and password don't match." };
    startSession(user);
    return { ok: true };
  },

  signUp(input: { name: string; email: string; password: string }): AuthResult {
    const email = input.email.trim().toLowerCase();
    if (state.users.some((u) => u.email.toLowerCase() === email)) return { ok: false, error: "An account with this email already exists. Sign in instead." };
    if (input.password.length < 8) return { ok: false, error: "Use at least 8 characters for your password." };

    const user: User = {
      id: `u_${id()}`, name: input.name.trim(), email,
      handle: makeHandle(input.name, [...state.users.map((u) => u.handle), ...state.bots.map((b) => b.handle)]),
      role: "admin", presence: "online",
    };
    set((st) => ({ ...st, passwords: { ...st.passwords, [email]: input.password } }));
    startSession(user);
    return { ok: true };
  },

  signOut() {
    saveSession(null);
    set((st) => ({ ...st, authStatus: "signed-out" }));
  },
};

export const actions = {
  ...authActions,

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
   * Creates a bot and its DM. The bot speaks first, so the chat never opens empty.
   * Returns the new thread's id so the screen can open it.
   */
  createBot(input: NewBotInput) {
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
  },

  /** Hire a ready-made bot from the marketplace, with safe defaults. */
  createBotFromTemplate(templateId: string) {
    const t = state.templates.find((x) => x.id === templateId);
    if (!t) return null;
    return actions.createBot({
      name: t.name, role: t.role, description: t.description, avatarColor: t.avatarColor,
      modelId: "m_claude", securityLevel: "ask-before-acting", computerMode: "own",
      instructions: "", monthlyBudgetUsd: 20,
    });
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

  updateOrg(patch: Partial<Pick<Org, "name" | "slug">>) {
    set((st) => ({ ...st, org: { ...st.org, ...patch } }));
  },

  updateCurrentUser(patch: Partial<Pick<User, "name" | "handle">>) {
    set((st) => ({ ...st, users: st.users.map((u) => (u.id === st.currentUserId ? { ...u, ...patch } : u)) }));
  },

  /** MOCK: adds the invited person straight away. The real API sends an email invite. */
  inviteMember(email: string, role: User["role"]) {
    const name = email.split("@")[0].replace(/[._-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    const handle = makeHandle(name, state.users.map((u) => u.handle));
    set((st) => ({ ...st, users: [...st.users, { id: `u_${id()}`, name, email, handle, role, presence: "offline" }] }));
  },

  changeMemberRole(userId: string, role: User["role"]) {
    set((st) => ({ ...st, users: st.users.map((u) => (u.id === userId ? { ...u, role } : u)) }));
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
    set(() => seed());
  },
};

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
export const useAuthStatus = () => useStore(useCallback((s: State) => s.authStatus, []));
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
export const useUsers = () => useStore(useCallback((s: State) => s.users, []));
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
