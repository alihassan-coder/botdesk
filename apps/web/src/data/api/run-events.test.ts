import { describe, expect, it } from "vitest";
import type { Message, Thread } from "../types";
import { applyRunEvent, type ChatSlice } from "./run-events";
import type { ApiMessage, ApiRunEvent } from "./types";

const thread: Thread = {
  id: "t1", kind: "dm", title: "Scout", botId: "b1", participants: [], lastMessageAt: "2026-11-12T09:00:00Z", lastMessagePreview: "", unread: 0,
};
const start: ChatSlice = { messages: [], threads: [thread], runs: [{ id: "r1", threadId: "t1" }] };

let nextId = 1;
const event = (e: Pick<ApiRunEvent, "kind" | "data"> & { runId?: string | null }) =>
  ({ id: nextId++, threadId: "t1", runId: "r1", createdAt: "2026-11-12T09:00:01Z", ...e }) as ApiRunEvent;
const play = (...events: ApiRunEvent[]) => events.reduce(applyRunEvent, start);
const only = (chat: ChatSlice): Partial<Message> => {
  expect(chat.messages).toHaveLength(1);
  const [m] = chat.messages;
  return { id: m.id, status: m.status, error: m.error, parts: m.parts };
};
const apiMessage = (id: string, text: string, author: ApiMessage["author"], createdAt: string): ApiMessage => ({
  id, threadId: "t1", author, parts: [{ type: "text", text }], status: "complete", createdAt,
});

const started = event({ kind: "run_started", data: { botId: "b1" } });
const delta = (text: string) => event({ kind: "message_delta", data: { messageId: "m1", botId: "b1", text } });
const failed = event({ kind: "run_failed", data: { status: "failed", error: "The model didn't answer." } });
const cancelled = event({ kind: "run_finished", data: { status: "cancelled" } });

describe("a chat's live updates", () => {
  it("run_started shows the bot thinking, with no words yet", () => {
    const chat = play(started);
    expect(only(chat)).toEqual({ id: "typing-r1", status: "streaming", error: undefined, parts: [{ type: "text", text: "" }] });
    expect(chat.runs).toEqual([{ id: "r1", threadId: "t1", botId: "b1" }]);
  });

  it("deltas turn the dots into the reply, chunk by chunk", () => {
    const chat = play(started, delta("Hel"), delta("lo"));
    expect(only(chat)).toMatchObject({ id: "m1", status: "streaming", parts: [{ type: "text", text: "Hello" }] });
    expect(chat.runs[0].messageId).toBe("m1");
  });

  it("message_saved replaces the streamed reply, and the chat list shows it", () => {
    const saved = apiMessage("m1", "Hello there", { type: "bot", id: "b1" }, "2026-11-12T09:00:02Z");
    const chat = play(started, delta("Hel"), event({ kind: "message_saved", data: { message: saved } }));
    expect(only(chat)).toMatchObject({ id: "m1", status: "complete", parts: [{ type: "text", text: "Hello there" }] });
    expect(chat.threads[0]).toMatchObject({ lastMessagePreview: "Hello there", lastMessageAt: "2026-11-12T09:00:02Z" });
  });

  it("a reply stopped before any words leaves nothing behind; one stopped midway keeps its words", () => {
    expect(play(started, cancelled)).toMatchObject({ messages: [], runs: [] });
    expect(only(play(started, delta("Half"), cancelled))).toMatchObject({ status: "complete", parts: [{ type: "text", text: "Half" }] });
  });

  it("run_failed marks the reply with the reason, even when no words came", () => {
    expect(only(play(started, failed))).toMatchObject({ id: "typing-r1", status: "error", error: "The model didn't answer." });
    expect(only(play(started, delta("Hm"), failed))).toMatchObject({ id: "m1", status: "error", parts: [{ type: "text", text: "Hm" }] });
    expect(play(started, failed).runs).toEqual([]);
  });

  it("your own saved message (no run) is added once, however often it arrives", () => {
    const mine = apiMessage("m5", "Hi", { type: "user", id: "u1" }, "2026-11-12T09:00:03Z");
    const saved = event({ kind: "message_saved", runId: null, data: { message: mine } });
    expect(play(saved, saved).messages.map((m) => m.id)).toEqual(["m5"]);
  });
});
