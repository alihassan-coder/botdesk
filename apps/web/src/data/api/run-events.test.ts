import { describe, expect, it } from "vitest";
import type { Message, Thread } from "../types";
import { toApproval, toMessage } from "./map";
import { applyRunEvent, withWaitingApprovals, type ChatSlice } from "./run-events";
import type { ApiApproval, ApiMessage, ApiRunEvent } from "./types";

const thread: Thread = {
  id: "t1", kind: "dm", title: "Scout", botId: "b1", participants: [], lastMessageAt: "2026-11-12T09:00:00Z", lastMessagePreview: "", unread: 0,
};
const start: ChatSlice = { messages: [], threads: [thread], runs: [{ id: "r1", threadId: "t1" }], approvals: [] };

let nextId = 1;
const event = (e: Pick<ApiRunEvent, "kind" | "data"> & { runId?: string | null }) =>
  ({ id: nextId++, threadId: "t1", runId: "r1", createdAt: "2026-11-12T09:00:01Z", ...e }) as ApiRunEvent;
const play = (...events: ApiRunEvent[]) => events.reduce(applyRunEvent, start);
const only = (chat: ChatSlice): Partial<Message> => {
  expect(chat.messages).toHaveLength(1);
  const [m] = chat.messages;
  return { id: m.id, status: m.status, error: m.error, parts: m.parts, author: m.author };
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
    expect(only(chat)).toMatchObject({ id: "typing-r1", status: "streaming", error: undefined, parts: [{ type: "text", text: "" }] });
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

/* ---------- Tools and approvals ---------- */

const apiApproval = (patch: Partial<ApiApproval> = {}): ApiApproval => ({
  id: "a1", runId: "r1", threadId: "t1", botId: "b1", toolExecutionId: "x1", tool: "demo.send_email",
  title: "Send an email", summary: "Send an email to sara@acme.dev: Launch", riskClass: "external-send",
  reason: "level=Ask before acting · risk=external-send · tainted=no → ask", tainted: false,
  args: { to: "sara@acme.dev", subject: "Launch", body: "" }, finalArgs: null, argsSchema: null,
  preview: [{ label: "To", value: "sara@acme.dev" }], status: "pending",
  requestedAt: "2026-11-12T09:00:01", expiresAt: "2026-11-15T09:00:01", decidedAt: null, decidedBy: null,
  ...patch,
});

const toolStarted = (id = "x0", tool = "demo.read_inbox") =>
  event({ kind: "tool_started", data: { toolExecutionId: id, tool, risk: "read", args: {} } });
const toolFinished = (status: "succeeded" | "failed" | "denied", id = "x0", error: string | null = null) =>
  event({ kind: "tool_finished", data: { toolExecutionId: id, tool: "demo.read_inbox", status, result: null, error } });
const requested = (patch: Partial<ApiApproval> = {}) => event({ kind: "approval_requested", data: { approval: apiApproval(patch) } });
const decided = (patch: Partial<ApiApproval>) => event({ kind: "approval_decided", data: { approval: apiApproval(patch) } });
const resumed = event({ kind: "run_resumed", data: { botId: "b1" } });
const needsAttention = event({ kind: "run_needs_attention", data: { status: "needs_attention", error: "Check the outbox." } });

describe("tools and approvals in a chat", () => {
  it("a tool call shows as a line above the reply's text, then its outcome", () => {
    const running = play(started, delta("Let me look. "), toolStarted());
    expect(only(running).parts).toEqual([
      { type: "tool-call", toolExecutionId: "x0", tool: "demo.read_inbox", status: "running" },
      { type: "text", text: "Let me look. " },
    ]);
    const done = applyRunEvent(running, toolFinished("succeeded"));
    expect(only(done).parts?.[0]).toEqual({ type: "tool-call", toolExecutionId: "x0", tool: "demo.read_inbox", status: "succeeded" });
  });

  it("a refused call (no tool_started) still gets its line, with why", () => {
    const chat = play(started, toolFinished("denied", "x9", "Not allowed at this level."));
    expect(only(chat).parts?.[0]).toMatchObject({ type: "tool-call", toolExecutionId: "x9", status: "denied", error: "Not allowed at this level." });
  });

  it("approval_requested puts the card in the reply, stores the approval and pauses the run", () => {
    const chat = play(started, delta("Sending now."), requested());
    expect(only(chat)).toMatchObject({ id: "m1", status: "complete", parts: [{ type: "approval", approvalId: "a1" }, { type: "text", text: "Sending now." }] });
    expect(chat.approvals).toEqual([toApproval(apiApproval())]);
    expect(chat.approvals[0].requestedAt).toBe("2026-11-12T09:00:01Z");
    expect(chat.runs).toEqual([{ id: "r1", threadId: "t1", botId: "b1", messageId: "m1", status: "waiting_approval" }]);
  });

  it("before any words, the card sits in the thinking reply, which stops showing dots", () => {
    const chat = play(started, requested());
    expect(only(chat)).toMatchObject({ id: "typing-r1", status: "complete", parts: [{ type: "approval", approvalId: "a1" }, { type: "text", text: "" }] });
  });

  it("approval_decided updates the card live; run_resumed has the bot thinking again", () => {
    const decidedBy = { id: "u1", name: "Ali" };
    const chat = play(started, requested(), decided({ status: "approved", decidedBy, decidedAt: "2026-11-12T09:01:00Z" }), resumed);
    expect(chat.approvals[0]).toMatchObject({ status: "approved", decidedBy: "u1", decidedByName: "Ali", decidedAt: "2026-11-12T09:01:00Z" });
    expect(chat.runs[0].status).toBe("running");
    expect(only(chat).status).toBe("streaming");
  });

  it("the resumed run's words take over the reply, and the saved reply keeps the card and tool lines", () => {
    const savedReply = {
      ...apiMessage("m1", "Sent.", { type: "bot", id: "b1" }, "2026-11-12T09:02:00Z"),
      parts: [{ type: "approval", approvalId: "a1" }, { type: "text", text: "Sent." }],
    };
    const chat = play(
      started, requested(), decided({ status: "approved" }), resumed,
      toolStarted("x1", "demo.send_email"), toolFinished("succeeded", "x1"), delta("Sent."),
      event({ kind: "message_saved", data: { message: savedReply } }),
    );
    expect(only(chat)).toMatchObject({
      id: "m1", status: "complete",
      parts: [{ type: "approval", approvalId: "a1" }, { type: "tool-call", toolExecutionId: "x1", status: "succeeded" }, { type: "text", text: "Sent." }],
    });
  });

  it("stopping a waiting run keeps the card, which shows it expired", () => {
    const chat = play(started, requested(), decided({ status: "expired" }), cancelled);
    expect(only(chat).parts?.[0]).toEqual({ type: "approval", approvalId: "a1" });
    expect(chat.approvals[0].status).toBe("expired");
    expect(chat.runs).toEqual([]);
  });

  it("run_needs_attention pauses the run with the reason", () => {
    const chat = play(started, delta("Sending"), needsAttention);
    expect(chat.runs[0]).toMatchObject({ status: "needs_attention", error: "Check the outbox." });
    expect(only(chat).status).toBe("complete");
  });

  it("an approval for a run we never saw start still shows, in a stand-in reply", () => {
    const chat = applyRunEvent({ ...start, runs: [] }, requested());
    expect(only(chat)).toMatchObject({ id: "typing-r1", author: { type: "bot", id: "b1" } });
    expect(chat.runs).toEqual([{ id: "r1", threadId: "t1", botId: "b1", status: "waiting_approval" }]);
  });
});

describe("withWaitingApprovals (a chat that just loaded)", () => {
  it("shows a waiting approval in a stand-in reply and marks its run as waiting", () => {
    const chat = withWaitingApprovals({ ...start, runs: [] }, [toApproval(apiApproval())]);
    expect(only(chat)).toMatchObject({ id: "typing-r1", status: "complete", parts: [{ type: "approval", approvalId: "a1" }, { type: "text", text: "" }] });
    expect(chat.runs).toEqual([{ id: "r1", threadId: "t1", botId: "b1", status: "waiting_approval" }]);
  });

  it("leaves decided approvals, and ones already in a message, to their messages", () => {
    const saved = toMessage({ ...apiMessage("m1", "Sent.", { type: "bot", id: "b1" }, "2026-11-12T09:02:00Z"), parts: [{ type: "approval", approvalId: "a1" }] });
    const approvals = [toApproval(apiApproval()), toApproval(apiApproval({ id: "a2", status: "denied" }))];
    const chat = withWaitingApprovals({ ...start, runs: [], messages: [saved] }, approvals);
    expect(chat.messages).toEqual([saved]);
    expect(chat.runs).toEqual([]);
    expect(chat.approvals.map((a) => a.id).sort()).toEqual(["a1", "a2"]);
  });
});
