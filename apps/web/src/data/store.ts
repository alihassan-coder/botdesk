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
import { parseMentions } from "@/lib/mentions";
import * as mock from "./mock/fixtures";
import type { Approval, ApprovalStatus, Bot, Message, Participant, Thread } from "./types";

interface State {
  org: typeof mock.org;
  users: typeof mock.users;
  currentUserId: string;
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

export const actions = {
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
    setTimeout(() => pushBotMessage(a.threadId, a.botId, [{ type: "text", text }]), 700);
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

  createBotFromTemplate(templateId: string) {
    const t = state.templates.find((x) => x.id === templateId);
    if (!t) return null;
    const botId = `b_${id()}`;
    const threadId = `t_${id()}`;
    const handle = t.name.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    set((st) => ({
      ...st,
      bots: [
        ...st.bots,
        {
          id: botId, name: t.name, handle, role: t.role, description: t.description, avatarColor: t.avatarColor,
          status: "idle", statusText: "Just hired", modelId: "m_claude", securityLevel: "ask-before-acting",
          computerMode: "own", connectionIds: [], instructions: "", createdAt: now(), monthlyBudgetUsd: 20, spentThisMonthUsd: 0,
        },
      ],
      threads: [
        {
          id: threadId, kind: "dm", title: t.name, botId,
          participants: [{ type: "user", id: st.currentUserId }, { type: "bot", id: botId }],
          lastMessageAt: now(), lastMessagePreview: "Hi! What should I work on first?", unread: 1,
        },
        ...st.threads,
      ],
      messages: [
        ...st.messages,
        { id: id(), threadId, author: { type: "bot", id: botId }, createdAt: now(), parts: [{ type: "text", text: `Hi! I'm ${t.name}. ${t.description} What should I work on first?` }] },
      ],
    }));
    return threadId;
  },

  reset() {
    set(() => seed());
  },
};

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

  setTimeout(() => {
    msgId = pushBotMessage(
      threadId,
      botId,
      [{ type: "reasoning", text: `Reading the request, checking ${bot.name}'s tools and memory, planning steps.`, durationSec: 2 }, { type: "text", text: "" }],
      "streaming",
    );
    const timer = setInterval(() => {
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
        clearInterval(timer);
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
