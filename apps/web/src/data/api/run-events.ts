import type { Message, Thread } from "../types";
import { asUtc, toMessage } from "./map";
import type { ApiRunEvent } from "./types";

/**
 * How a chat's live updates change what the web app shows. Pure, so it's easy to test;
 * store.ts feeds it every event from the chat's event stream.
 *
 * A reply goes like this: `run_started` (the bot is thinking), `message_delta`s (words
 * arrive), then `message_saved` (the finished reply) and `run_finished`. Or `run_failed`.
 */

/** A bot reply in progress. Known from the moment you send, so the Stop button can show. */
export interface ActiveRun {
  id: string;
  threadId: string;
  /** Known once the run has started. */
  botId?: string;
  /** The reply's id, known once its first words arrive. */
  messageId?: string;
}

export interface ChatSlice {
  messages: Message[];
  threads: Thread[];
  runs: ActiveRun[];
}

/** Stands in for a reply that has started but has no words yet: it shows as typing dots. */
export const typingId = (runId: string) => `typing-${runId}`;

export function applyRunEvent(chat: ChatSlice, event: ApiRunEvent): ChatSlice {
  const run = chat.runs.find((r) => r.id === event.runId);

  switch (event.kind) {
    case "message_saved": {
      const message = toMessage(event.data.message);
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
      // Stopped before any words: drop the dots. Stopped mid-reply: keep what was written.
      const messages = chat.messages
        .filter((m) => !event.runId || m.id !== typingId(event.runId))
        .map((m) => (m.id === run?.messageId && m.status === "streaming" ? { ...m, status: "complete" as const } : m));
      return { ...chat, messages, runs: chat.runs.filter((r) => r.id !== event.runId) };
    }

    case "run_failed": {
      const runs = chat.runs.filter((r) => r.id !== event.runId);
      const failedId = run?.messageId ?? (event.runId ? typingId(event.runId) : undefined);
      const failed = chat.messages.find((m) => m.id === failedId);
      if (failed) {
        const messages = chat.messages.map((m) => (m === failed ? { ...m, status: "error" as const, error: event.data.error } : m));
        return { ...chat, messages, runs };
      }
      // The failure is all we heard of this reply (say, it never started): still say so.
      const botId = run?.botId;
      if (!botId || !failedId) return { ...chat, runs };
      const notice: Message = {
        id: failedId, threadId: event.threadId, author: { type: "bot", id: botId },
        parts: [], status: "error", error: event.data.error, createdAt: asUtc(event.createdAt),
      };
      return { ...chat, messages: [...chat.messages, notice], runs };
    }

    default:
      return chat;
  }
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
