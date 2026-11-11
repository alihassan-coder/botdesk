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
import * as mock from "./mock/fixtures";
import type { Approval, ApprovalStatus, Bot, Message, Thread } from "./types";

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

const MENTION = /@([a-z0-9_-]+)/gi;

export const actions = {
  sendMessage(threadId: string, text: string) {
    const s = state;
    const mentions = [...text.matchAll(MENTION)]
      .map(([, h]) => {
        const bot = s.bots.find((b) => b.handle === h.toLowerCase());
        if (bot) return { type: "bot" as const, id: bot.id };
        const user = s.users.find((u) => u.handle === h.toLowerCase());
        return user ? { type: "user" as const, id: user.id } : null;
      })
      .filter((m) => m !== null);

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

    // MOCK: pick who replies: a mentioned bot, else the DM's bot.
    const thread = s.threads.find((t) => t.id === threadId);
    const replyBotId =
      mentions.find((m) => m.type === "bot")?.id ?? thread?.botId ?? thread?.participants.find((p) => p.type === "bot")?.id;
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
    if (a) {
      const text =
        status === "approved" ? `Approved. Done: ${a.title.toLowerCase()}.` : `Okay, I won't ${a.title.toLowerCase()}.`;
      setTimeout(() => pushBotMessage(a.threadId, a.botId, [{ type: "text", text }]), 700);
    }
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
