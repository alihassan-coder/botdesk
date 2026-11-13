import type { Approval, Message, MessagePart, Thread, ToolCallPart } from "../types";
import { asUtc, toApproval, toMessage } from "./map";
import type { ApiRun, ApiRunEvent } from "./types";

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
 * Cards and tool lines sit above the reply's text in the order they arrived, which is the
 * order the saved reply has them too, so nothing jumps when the reply is saved.
 *
 * A chat that opens mid-reply replays the streaming (queued or running) runs' events from their
 * start (see `replayFrom` in withActiveRuns), so events can arrive twice. Every event is safe to apply
 * again except `message_delta`, which adds words: a run remembers the newest event id it has
 * seen, and a delta at or below it is skipped.
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
  /** The newest of its events this chat has applied (event ids only grow within a chat). */
  lastEventId?: number;
}

export interface ChatSlice {
  messages: Message[];
  threads: Thread[];
  runs: ActiveRun[];
  approvals: Approval[];
  /** Runs seen finish (newest last). A late or replayed event can't bring one back as paused. */
  endedRunIds?: string[];
}

/** How many ended run ids to remember: enough for any replay after a reconnect. */
const ENDED_RUNS_KEPT = 200;

/** Stands in for a reply that has started but has no words yet: it shows as typing dots. */
export const typingId = (runId: string) => `typing-${runId}`;

export function applyRunEvent(chat: ChatSlice, event: ApiRunEvent): ChatSlice {
  const next = reduce(chat, event);
  return event.runId ? withLastEventId(next, event.runId, event.id) : next;
}

function reduce(chat: ChatSlice, event: ApiRunEvent): ChatSlice {
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
      if (!event.runId || hasEnded(chat, event.runId)) return chat; // a replay of a run that has ended
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
      // Words already added (a replay), or words for a reply that isn't being written: one that's
      // saved (its text is whole) or paused (a run resumes, which sets it streaming, before more words).
      if (run?.lastEventId !== undefined && event.id <= run.lastEventId) return chat;
      if (event.runId && hasEnded(chat, event.runId)) return chat;
      if (chat.messages.some((m) => m.id === messageId && m.status === "complete")) return chat;
      const placeholder = event.runId ? typingId(event.runId) : undefined;
      const existing = chat.messages.find((m) => m.id === messageId || m.id === placeholder);
      const reply: Message = existing
        ? { ...existing, id: messageId, status: "streaming", parts: appendText(existing.parts, text) }
        : { id: messageId, threadId: event.threadId, author: { type: "bot", id: botId }, parts: [{ type: "text", text }], status: "streaming", createdAt: asUtc(event.createdAt) };
      const messages = existing ? chat.messages.map((m) => (m === existing ? reply : m)) : [...chat.messages, reply];
      const runs = event.runId ? upsertRun(chat.runs, { ...run, id: event.runId, threadId: event.threadId, botId, messageId }) : chat.runs;
      return { ...chat, messages, runs };
    }

    case "run_finished":
      return event.runId ? endRun(chat, event.runId) : chat;

    case "run_failed": {
      const runs = chat.runs.filter((r) => r.id !== event.runId);
      const endedRunIds = ended(chat, event.runId);
      const failed = event.runId ? replyOf(chat, event.runId) : undefined;
      if (failed) {
        const messages = chat.messages.map((m) => (m === failed ? { ...m, status: "error" as const, ...failure(event.data) } : m));
        return { ...chat, messages, runs, endedRunIds };
      }
      // The failure is all we heard of this reply (say, it never started): still say so.
      const botId = run?.botId;
      if (!botId || !event.runId) return { ...chat, runs, endedRunIds };
      const notice: Message = {
        id: typingId(event.runId), threadId: event.threadId, author: { type: "bot", id: botId },
        parts: [], status: "error", ...failure(event.data), createdAt: asUtc(event.createdAt),
      };
      return { ...chat, messages: [...chat.messages, notice], runs, endedRunIds };
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
      // Already decided (a late or replayed event): show the card, but the run isn't waiting on it.
      const stored = withCard.approvals.find((a) => a.id === approval.id);
      if (stored?.status !== "pending") return withCard;
      return pauseRun(withCard, event.runId, event.threadId, approval.botId, { status: "waiting_approval" });
    }

    case "approval_decided":
      return { ...chat, approvals: upsertApproval(chat.approvals, toApproval(event.data.approval)) };

    case "run_resumed": {
      if (!event.runId || hasEnded(chat, event.runId)) return chat;
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

/** Why a reply failed, and whether it was the budget (the chat then offers a way to raise it). */
function failure({ error, code }: { error: string; code?: "budget" }): Pick<Message, "error" | "errorCode"> {
  return code === "budget" ? { error, errorCode: "budget" } : { error };
}

/**
 * Approvals that arrived from the list when a chat opened. A reply still being written isn't
 * saved yet, so its cards would have nowhere to show: they go into a stand-in reply (the run's
 * typingId), which the run's next words take over.
 *
 * `activeRuns` (from the active-runs list, see withActiveRuns) says which runs are still going:
 * each of their cards shows, decided or not, and the runs' own status comes from that list.
 * Without it (the list failed), a pending approval's run counts as waiting, as a best guess.
 * Approvals already known as decided stay decided (see upsertApproval).
 */
export function withWaitingApprovals(chat: ChatSlice, approvals: Approval[], activeRuns?: ApiRun[]): ChatSlice {
  let next: ChatSlice = { ...chat, approvals: approvals.reduce(upsertApproval, chat.approvals) };
  const active = activeRuns && new Set(activeRuns.map((r) => r.id));
  for (const { id } of approvals) {
    const approval = next.approvals.find((a) => a.id === id)!;
    if (!approval.runId || hasEnded(next, approval.runId)) continue;
    if (active ? !active.has(approval.runId) : approval.status !== "pending") continue;
    const shown = next.messages.some((m) => m.parts.some((p) => p.type === "approval" && p.approvalId === approval.id));
    if (shown) continue;
    const event = { runId: approval.runId, threadId: approval.threadId, createdAt: approval.requestedAt };
    next = withRunCard(next, event, approval.botId, { type: "approval", approvalId: approval.id });
    if (!active) next = pauseRun(next, approval.runId, approval.threadId, approval.botId, { status: "waiting_approval" });
  }
  return next;
}

/**
 * A chat that just opened, told which of its runs are still going (`GET /threads/{id}/runs?active=true`).
 * That list sets this chat's runs: a running one shows the bot thinking, a paused one waits for a
 * decision or for a person (the needs-attention notice, with Stop). Runs we thought were going but
 * aren't in it have ended, except ones the list may predate: one you just started, or one heard
 * on the stream after the list's `lastEventId`.
 *
 * The stream follows from the list's `replayFrom`, so it replays the running runs' events from
 * their start: their words so far and tool lines. A paused run isn't replayed (it may wait for
 * days): it's rebuilt from this list and the approvals list (its card), and its words come with
 * the saved reply. A run the stream has already applied events for is left to the stream.
 */
export function withActiveRuns(chat: ChatSlice, threadId: string, apiRuns: ApiRun[], lastEventId?: number): ChatSlice {
  const listed = new Set(apiRuns.map((r) => r.id));
  const justSent = (r: ActiveRun) => r.botId === undefined && r.status === undefined;
  // Heard on the stream after the list was read: newer than the list (say, it started meanwhile).
  const newerThanList = (r: ActiveRun) => lastEventId !== undefined && (r.lastEventId ?? 0) > lastEventId;
  const over = chat.runs.filter((r) => r.threadId === threadId && !listed.has(r.id) && !justSent(r) && !newerThanList(r));
  let next = over.reduce((c, r) => endRun(c, r.id), chat);
  for (const apiRun of apiRuns) {
    if (hasEnded(next, apiRun.id)) continue;
    // The stream already has this run, and it replays all the run's events (it follows from
    // `replayFrom`), so what it shows is at least as new as the list.
    if (next.runs.find((r) => r.id === apiRun.id)?.lastEventId !== undefined) continue;
    if (apiRun.status === "waiting_approval" || apiRun.status === "needs_attention") {
      const error = apiRun.status === "needs_attention" ? (apiRun.error ?? undefined) : undefined;
      next = pauseRun(next, apiRun.id, threadId, apiRun.botId, { status: apiRun.status, error });
      continue;
    }
    const known = next.runs.find((r) => r.id === apiRun.id);
    const running: ActiveRun = { ...known, id: apiRun.id, threadId, botId: apiRun.botId, status: undefined, error: undefined };
    next = { ...next, runs: upsertRun(next.runs, running) };
    if (apiRun.status === "running" && !replyOf(next, apiRun.id)) {
      const typing: Message = {
        id: typingId(apiRun.id), threadId, author: { type: "bot", id: apiRun.botId },
        parts: [{ type: "text", text: "" }], status: "streaming", createdAt: asUtc(apiRun.startedAt ?? apiRun.createdAt),
      };
      next = { ...next, messages: [...next.messages, typing] };
    }
  }
  return next;
}

/**
 * Adds an approval (newest first), or replaces the one with its id in place. A decision is
 * final: an older "pending" copy (a slow list, a replayed event) never undoes it.
 */
export function upsertApproval(approvals: Approval[], approval: Approval): Approval[] {
  const known = approvals.find((a) => a.id === approval.id);
  if (!known) return [approval, ...approvals];
  if (known.status !== "pending" && approval.status === "pending") return approvals;
  return approvals.map((a) => (a.id === approval.id ? approval : a));
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

/** The run has ended: it stops being active, and its reply stops typing. */
function endRun(chat: ChatSlice, runId: string): ChatSlice {
  const run = chat.runs.find((r) => r.id === runId);
  // Stopped before any words: drop the dots (unless a card is there). Stopped mid-reply: keep what was written.
  const messages = chat.messages
    .filter((m) => m.id !== typingId(runId) || hasCards(m))
    .map((m) =>
      m.status === "streaming" && (m.id === run?.messageId || m.id === typingId(runId)) ? { ...m, status: "complete" as const } : m,
    );
  return { ...chat, messages, runs: chat.runs.filter((r) => r.id !== runId), endedRunIds: ended(chat, runId) };
}

function withLastEventId(chat: ChatSlice, runId: string, eventId: number): ChatSlice {
  const run = chat.runs.find((r) => r.id === runId);
  if (!run || (run.lastEventId ?? 0) >= eventId) return chat;
  return { ...chat, runs: chat.runs.map((r) => (r === run ? { ...r, lastEventId: eventId } : r)) };
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
 * (the chat opened mid-run) gets a stand-in reply to hold it; a run that already finished doesn't.
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
  if (!botId || hasEnded(chat, event.runId)) return chat; // a finished run's cards are in its saved reply
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

/**
 * The saved reply has its tool lines, in the order they showed live, so it's used as it is.
 * A reply saved by an older API has none: keep the ones we showed, after its approval cards.
 */
function withToolLines(saved: MessagePart[], streamed: MessagePart[]): MessagePart[] {
  const lines = streamed.filter((p) => p.type === "tool-call");
  if (lines.length === 0 || saved.some((p) => p.type === "tool-call")) return saved;
  return [...saved.filter((p) => p.type === "approval"), ...lines, ...saved.filter((p) => p.type !== "approval")];
}

function hasEnded(chat: ChatSlice, runId: string): boolean {
  return chat.endedRunIds?.includes(runId) ?? false;
}

function ended(chat: ChatSlice, runId: string | null): string[] | undefined {
  if (!runId || hasEnded(chat, runId)) return chat.endedRunIds;
  return [...(chat.endedRunIds ?? []), runId].slice(-ENDED_RUNS_KEPT);
}

/**
 * A paused run stays active (Stop still works) but isn't typing, so its reply stops "streaming".
 * A run already seen finish stays finished.
 */
function pauseRun(
  chat: ChatSlice,
  runId: string | null,
  threadId: string,
  botId: string | undefined,
  pause: Pick<ActiveRun, "status" | "error">,
): ChatSlice {
  if (!runId || hasEnded(chat, runId)) return chat;
  const run = chat.runs.find((r) => r.id === runId);
  const paused: ActiveRun = { ...run, id: runId, threadId, ...(botId ? { botId } : {}), ...pause };
  const reply = replyOf(chat, runId);
  const messages = chat.messages.map((m) => (m === reply ? { ...m, status: "complete" as const } : m));
  return { ...chat, messages, runs: upsertRun(chat.runs, paused) };
}
