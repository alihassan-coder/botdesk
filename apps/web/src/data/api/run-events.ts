import type { Approval, Message, MessagePart, Thread, ToolCallPart } from "../types";
import { asUtc, toApproval, toMessage } from "./map";
import type { ApiRunEvent } from "./types";

/**
 * How a chat's live updates change what the web app shows. Pure, so it's easy to test;
 * store.ts feeds it every event from the chat's event stream.
 *
 * A reply goes like this: `run_started` (the bot is thinking), `message_delta`s (words
 * arrive), then `message_saved` (the finished reply) and `run_finished`. Or `run_failed`.
 *
 * Tools and approvals add to that. `tool_started` / `tool_finished` show as a line in the
 * reply ("Used Send email · done"). A risky call pauses the run with `approval_requested`
 * (its card goes into the reply), someone decides (`approval_decided`), and the run carries
 * on with `run_resumed`. A run that may have half done something stops with
 * `run_needs_attention` until a person stops it.
 *
 * Cards and tool lines sit above the reply's text, in the order the saved reply has them
 * (its approval parts come first), so nothing jumps when the reply is saved.
 */

/** A bot reply in progress. Known from the moment you send, so the Stop button can show. */
export interface ActiveRun {
  id: string;
  threadId: string;
  /** Known once the run has started. */
  botId?: string;
  /** The reply's id, known once its first words arrive. */
  messageId?: string;
  /** Unset means running. A paused run waits for a decision, or for a person to check on it. */
  status?: "running" | "waiting_approval" | "needs_attention";
  /** Why it needs attention. */
  error?: string;
}

export interface ChatSlice {
  messages: Message[];
  threads: Thread[];
  runs: ActiveRun[];
  approvals: Approval[];
}

/** Stands in for a reply that has started but has no words yet: it shows as typing dots. */
export const typingId = (runId: string) => `typing-${runId}`;

export function applyRunEvent(chat: ChatSlice, event: ApiRunEvent): ChatSlice {
  const run = chat.runs.find((r) => r.id === event.runId);

  switch (event.kind) {
    case "message_saved": {
      const saved = toMessage(event.data.message);
      const streamed = chat.messages.find((m) => m.id === saved.id || (event.runId !== null && m.id === typingId(event.runId)));
      const message = streamed ? { ...saved, parts: withToolLines(saved.parts, streamed.parts) } : saved;
      const messages = chat.messages.filter((m) => !event.runId || m.id !== typingId(event.runId));
      return { ...chat, messages: upsertMessage(messages, message), threads: withPreview(chat.threads, message) };
    }

    case "run_started": {
      if (!event.runId) return chat;
      const started: ActiveRun = { ...run, id: event.runId, threadId: event.threadId, botId: event.data.botId };
      const hasReply = chat.messages.some((m) => m.id === run?.messageId || m.id === typingId(event.runId!));
      const typing: Message = {
        id: typingId(event.runId), threadId: event.threadId, author: { type: "bot", id: event.data.botId },
        parts: [{ type: "text", text: "" }], status: "streaming", createdAt: asUtc(event.createdAt),
      };
      return { ...chat, runs: upsertRun(chat.runs, started), messages: hasReply ? chat.messages : [...chat.messages, typing] };
    }

    case "message_delta": {
      const { messageId, botId, text } = event.data;
      const placeholder = event.runId ? typingId(event.runId) : undefined;
      const existing = chat.messages.find((m) => m.id === messageId || m.id === placeholder);
      const reply: Message = existing
        ? { ...existing, id: messageId, status: "streaming", parts: appendText(existing.parts, text) }
        : { id: messageId, threadId: event.threadId, author: { type: "bot", id: botId }, parts: [{ type: "text", text }], status: "streaming", createdAt: asUtc(event.createdAt) };
      const messages = existing ? chat.messages.map((m) => (m === existing ? reply : m)) : [...chat.messages, reply];
      const runs = event.runId ? upsertRun(chat.runs, { ...run, id: event.runId, threadId: event.threadId, botId, messageId }) : chat.runs;
      return { ...chat, messages, runs };
    }

    case "run_finished": {
      // Stopped before any words: drop the dots (unless a card is there). Stopped mid-reply: keep what was written.
      const messages = chat.messages
        .filter((m) => !event.runId || m.id !== typingId(event.runId) || hasCards(m))
        .map((m) =>
          m.status === "streaming" && (m.id === run?.messageId || (event.runId && m.id === typingId(event.runId)))
            ? { ...m, status: "complete" as const }
            : m,
        );
      return { ...chat, messages, runs: chat.runs.filter((r) => r.id !== event.runId) };
    }

    case "run_failed": {
      const runs = chat.runs.filter((r) => r.id !== event.runId);
      const failed = event.runId ? replyOf(chat, event.runId) : undefined;
      if (failed) {
        const messages = chat.messages.map((m) => (m === failed ? { ...m, status: "error" as const, error: event.data.error } : m));
        return { ...chat, messages, runs };
      }
      // The failure is all we heard of this reply (say, it never started): still say so.
      const botId = run?.botId;
      if (!botId || !event.runId) return { ...chat, runs };
      const notice: Message = {
        id: typingId(event.runId), threadId: event.threadId, author: { type: "bot", id: botId },
        parts: [], status: "error", error: event.data.error, createdAt: asUtc(event.createdAt),
      };
      return { ...chat, messages: [...chat.messages, notice], runs };
    }

    case "tool_started": {
      const { toolExecutionId, tool } = event.data;
      return withRunCard(chat, event, run?.botId, { type: "tool-call", toolExecutionId, tool, status: "running" });
    }

    case "tool_finished": {
      const { toolExecutionId, tool, status, error } = event.data;
      const line: ToolCallPart = { type: "tool-call", toolExecutionId, tool, status, ...(error ? { error } : {}) };
      return withRunCard(chat, event, run?.botId, line);
    }

    case "approval_requested": {
      const approval = toApproval(event.data.approval);
      const withCard = withRunCard({ ...chat, approvals: upsertApproval(chat.approvals, approval) }, event, approval.botId, {
        type: "approval", approvalId: approval.id,
      });
      return pauseRun(withCard, event.runId, event.threadId, approval.botId, { status: "waiting_approval" });
    }

    case "approval_decided":
      return { ...chat, approvals: upsertApproval(chat.approvals, toApproval(event.data.approval)) };

    case "run_resumed": {
      if (!event.runId) return chat;
      const resumed: ActiveRun = { ...run, id: event.runId, threadId: event.threadId, botId: event.data.botId, status: "running", error: undefined };
      const reply = replyOf(chat, event.runId);
      const messages = chat.messages.map((m) => (m === reply ? { ...m, status: "streaming" as const } : m));
      return { ...chat, messages, runs: upsertRun(chat.runs, resumed) };
    }

    case "run_needs_attention":
      return pauseRun(chat, event.runId, event.threadId, run?.botId, { status: "needs_attention", error: event.data.error });

    default:
      return chat;
  }
}

/**
 * Approvals that arrived from the list when a chat opened. A paused reply isn't saved yet, so
 * a waiting card would have nowhere to show: it goes into a stand-in reply (the run's typingId),
 * which the run's next words take over when it resumes. Its run counts as active again, waiting.
 */
export function withWaitingApprovals(chat: ChatSlice, approvals: Approval[]): ChatSlice {
  let next: ChatSlice = { ...chat, approvals: approvals.reduce(upsertApproval, chat.approvals) };
  for (const approval of approvals) {
    if (approval.status !== "pending" || !approval.runId) continue;
    const shown = next.messages.some((m) => m.parts.some((p) => p.type === "approval" && p.approvalId === approval.id));
    if (shown) continue;
    const event = { runId: approval.runId, threadId: approval.threadId, createdAt: approval.requestedAt };
    next = withRunCard(next, event, approval.botId, { type: "approval", approvalId: approval.id });
    next = pauseRun(next, approval.runId, approval.threadId, approval.botId, { status: "waiting_approval" });
  }
  return next;
}

/** Adds an approval (newest first), or replaces the one with its id in place. */
export function upsertApproval(approvals: Approval[], approval: Approval): Approval[] {
  return approvals.some((a) => a.id === approval.id)
    ? approvals.map((a) => (a.id === approval.id ? approval : a))
    : [approval, ...approvals];
}

/** Adds the message, or replaces the one with its id in place, so the order stays put. */
export function upsertMessage(messages: Message[], message: Message): Message[] {
  return messages.some((m) => m.id === message.id)
    ? messages.map((m) => (m.id === message.id ? message : m))
    : [...messages, message];
}

/** A chat's row in the list shows its newest message. */
export function withPreview(threads: Thread[], message: Message): Thread[] {
  const text = message.parts.flatMap((p) => (p.type === "text" ? [p.text] : [])).join("\n");
  if (!text) return threads;
  return threads.map((t) =>
    t.id === message.threadId && Date.parse(message.createdAt) >= Date.parse(t.lastMessageAt)
      ? { ...t, lastMessageAt: message.createdAt, lastMessagePreview: text }
      : t,
  );
}

function upsertRun(runs: ActiveRun[], run: ActiveRun): ActiveRun[] {
  return runs.some((r) => r.id === run.id) ? runs.map((r) => (r.id === run.id ? run : r)) : [...runs, run];
}

function appendText(parts: Message["parts"], text: string): Message["parts"] {
  const last = parts.findLastIndex((p) => p.type === "text");
  if (last === -1) return [...parts, { type: "text", text }];
  return parts.map((p, i) => (i === last && p.type === "text" ? { ...p, text: p.text + text } : p));
}

/** The reply a run is writing: the one with its words, or the stand-in before any arrive. */
function replyOf(chat: ChatSlice, runId: string): Message | undefined {
  const messageId = chat.runs.find((r) => r.id === runId)?.messageId;
  return chat.messages.find((m) => (messageId !== undefined && m.id === messageId) || m.id === typingId(runId));
}

const hasCards = (message: Message) => message.parts.some((p) => p.type === "approval" || p.type === "tool-call");

/**
 * Puts a card (an approval, or a tool line) into the run's reply. A run we hadn't heard of
 * (the chat opened mid-run) gets a stand-in reply to hold it.
 */
function withRunCard(
  chat: ChatSlice,
  event: { runId: string | null; threadId: string; createdAt: string },
  botId: string | undefined,
  card: MessagePart,
): ChatSlice {
  if (!event.runId) return chat;
  const reply = replyOf(chat, event.runId);
  if (reply) {
    return { ...chat, messages: chat.messages.map((m) => (m === reply ? { ...m, parts: putCard(m.parts, card) } : m)) };
  }
  if (!botId) return chat;
  const standIn: Message = {
    id: typingId(event.runId), threadId: event.threadId, author: { type: "bot", id: botId },
    parts: [card, { type: "text", text: "" }], status: "streaming", createdAt: asUtc(event.createdAt),
  };
  return { ...chat, messages: [...chat.messages, standIn] };
}

/** The same card again (same approval or tool call) replaces it; a new one goes above the text. */
function putCard(parts: MessagePart[], card: MessagePart): MessagePart[] {
  const at = parts.findIndex((p) => sameCard(p, card));
  if (at !== -1) return parts.map((p, i) => (i === at ? card : p));
  const firstText = parts.findIndex((p) => p.type === "text");
  return firstText === -1 ? [...parts, card] : [...parts.slice(0, firstText), card, ...parts.slice(firstText)];
}

function sameCard(a: MessagePart, b: MessagePart) {
  if (a.type === "approval" && b.type === "approval") return a.approvalId === b.approvalId;
  if (a.type === "tool-call" && b.type === "tool-call") return a.toolExecutionId === b.toolExecutionId;
  return false;
}

/** The saved reply has no tool lines; keep the ones we showed, after its approval cards. */
function withToolLines(saved: MessagePart[], streamed: MessagePart[]): MessagePart[] {
  const lines = streamed.filter((p) => p.type === "tool-call");
  if (lines.length === 0) return saved;
  return [...saved.filter((p) => p.type === "approval"), ...lines, ...saved.filter((p) => p.type !== "approval")];
}

/** A paused run stays active (Stop still works) but isn't typing, so its reply stops "streaming". */
function pauseRun(
  chat: ChatSlice,
  runId: string | null,
  threadId: string,
  botId: string | undefined,
  pause: Pick<ActiveRun, "status" | "error">,
): ChatSlice {
  if (!runId) return chat;
  const run = chat.runs.find((r) => r.id === runId);
  const paused: ActiveRun = { ...run, id: runId, threadId, ...(botId ? { botId } : {}), ...pause };
  const reply = replyOf(chat, runId);
  const messages = chat.messages.map((m) => (m === reply ? { ...m, status: "complete" as const } : m));
  return { ...chat, messages, runs: upsertRun(chat.runs, paused) };
}
