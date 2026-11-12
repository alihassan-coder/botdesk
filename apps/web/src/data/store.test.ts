import { describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot as state } from "./store";

/** Lets the mock bot finish "thinking" and streaming its reply. */
const finishBotReply = () => vi.advanceTimersByTime(10_000);
const messagesIn = (threadId: string) => state().messages.filter((m) => m.threadId === threadId);
const lastMessageIn = (threadId: string) => messagesIn(threadId).at(-1)!;

describe("sendMessage", () => {
  it("adds your message and updates the thread preview", () => {
    actions.sendMessage("t_sales", "Pause tonight's run.");

    const message = lastMessageIn("t_sales");
    expect(message.author).toEqual({ type: "user", id: "u_me" });
    expect(message.parts).toEqual([{ type: "text", text: "Pause tonight's run." }]);
    expect(state().threads.find((t) => t.id === "t_sales")?.lastMessagePreview).toBe("Pause tonight's run.");
  });

  it("records who was @mentioned", () => {
    actions.sendMessage("t_launch", "@sara and @bugs, status?");
    expect(lastMessageIn("t_launch").mentions).toEqual([
      { type: "user", id: "u_sara" },
      { type: "bot", id: "b_bugs" },
    ]);
  });

  it("in a DM, the DM's bot replies even if another bot is mentioned", () => {
    vi.useFakeTimers();
    actions.sendMessage("t_chief", "Ask @inbox for a summary.");
    finishBotReply();

    const reply = lastMessageIn("t_chief");
    expect(reply.author).toEqual({ type: "bot", id: "b_chief" });
    expect(reply.status).toBe("complete");
  });

  it("in a group, the mentioned bot replies", () => {
    vi.useFakeTimers();
    actions.sendMessage("t_launch", "@sales hold the emails.");
    finishBotReply();

    expect(lastMessageIn("t_launch").author).toEqual({ type: "bot", id: "b_sales" });
  });

  it("shows the bot working while it replies, then idle", () => {
    vi.useFakeTimers();
    actions.sendMessage("t_sales", "Hi");
    expect(state().bots.find((b) => b.id === "b_sales")?.status).toBe("working");

    finishBotReply();
    expect(state().bots.find((b) => b.id === "b_sales")?.status).toBe("idle");
  });
});

describe("decideApproval", () => {
  it("records the decision and who made it", () => {
    actions.decideApproval("a_1", "approved");
    const approval = state().approvals.find((a) => a.id === "a_1");
    expect(approval?.status).toBe("approved");
    expect(approval?.decidedBy).toBe("u_me");
  });

  it("keeps the bot's status in step with what's still waiting", () => {
    actions.decideApproval("a_1", "approved");
    expect(state().bots.find((b) => b.id === "b_inbox")?.statusText).toBe("1 waiting for you");

    actions.decideApproval("a_2", "denied");
    const inbox = state().bots.find((b) => b.id === "b_inbox");
    expect(inbox?.status).toBe("idle");
    expect(inbox?.statusText).toBe("All caught up");
  });

  it("has the bot confirm in the thread", () => {
    vi.useFakeTimers();
    actions.decideApproval("a_2", "denied");
    vi.advanceTimersByTime(1_000);
    expect(lastMessageIn("t_inbox").parts[0]).toEqual({
      type: "text",
      text: "Okay, I won't go ahead with “Decline vendor demo (Initech)”.",
    });
  });
});

describe("editAndApprove", () => {
  it("saves your edits and approves the edited version", () => {
    actions.editAndApprove("a_1", [{ label: "Body", value: "Thursday works. Best, Ali" }]);
    const approval = state().approvals.find((a) => a.id === "a_1");
    expect(approval?.preview).toEqual([{ label: "Body", value: "Thursday works. Best, Ali" }]);
    expect(approval?.status).toBe("approved");
  });
});

describe("smaller actions", () => {
  it("answerQuestion stores the chosen option", () => {
    actions.answerQuestion("m13", "No");
    const part = state().messages.find((m) => m.id === "m13")?.parts[0];
    expect(part).toMatchObject({ type: "question", answered: "No" });
  });

  it("markRead clears the unread count", () => {
    actions.markRead("t_inbox");
    expect(state().threads.find((t) => t.id === "t_inbox")?.unread).toBe(0);
  });

  it("toggleRoutine switches a routine on and off", () => {
    actions.toggleRoutine("r_1");
    expect(state().routines.find((r) => r.id === "r_1")?.enabled).toBe(false);
    actions.toggleRoutine("r_1");
    expect(state().routines.find((r) => r.id === "r_1")?.enabled).toBe(true);
  });

  it("deleteMemory forgets a memory", () => {
    actions.deleteMemory("mem_1");
    expect(state().memories.some((m) => m.id === "mem_1")).toBe(false);
  });

  it("createBotFromTemplate hires the bot and opens a chat where it speaks first", () => {
    const threadId = actions.createBotFromTemplate("tpl_inbox");
    const thread = state().threads.find((t) => t.id === threadId);

    expect(thread?.kind).toBe("dm");
    expect(state().bots.find((b) => b.id === thread?.botId)?.name).toBe("Inbox Zero");
    expect(messagesIn(threadId!)[0].author.type).toBe("bot");
  });

  it("createBot builds a bot from your choices, with a unique handle", () => {
    const threadId = actions.createBot({
      name: "Chief", role: "Second chief", description: "", avatarColor: "rose", instructions: "Be brief.",
      modelId: "m_gpt", securityLevel: "read-only", computerMode: "none", monthlyBudgetUsd: 10,
    });
    const bot = state().bots.find((b) => b.id === state().threads.find((t) => t.id === threadId)?.botId);

    expect(bot).toMatchObject({ handle: "chief-2", modelId: "m_gpt", securityLevel: "read-only", spentThisMonthUsd: 0, status: "idle" });
    expect(messagesIn(threadId)[0].parts[0]).toMatchObject({ type: "text", text: expect.stringContaining("Second chief") });
  });

  it("createRoutine saves it and the bot confirms in its chat", () => {
    const routineId = actions.createRoutine({
      botId: "b_expense", name: "Friday report", description: "", schedule: "Every Friday at 5 PM", steps: ["Find receipts", "File"], enabled: true,
    });
    expect(state().routines.find((r) => r.id === routineId)).toMatchObject({ name: "Friday report", source: "edit", enabled: true });

    const confirmation = lastMessageIn("t_expense");
    expect(confirmation.parts[0]).toEqual({ type: "routine-created", routineId, name: "Friday report" });
    expect(confirmation.parts[1]).toMatchObject({ text: "Got it. I'll run “Friday report” every Friday at 5 PM." });
  });

  it("updateOrg renames the organization", () => {
    actions.updateOrg({ name: "Acme Inc", slug: "acme-inc" });
    expect(state().org).toMatchObject({ name: "Acme Inc", slug: "acme-inc" });
  });

  it("updateCurrentUser renames you", () => {
    actions.updateCurrentUser({ name: "Ali H.", handle: "alih" });
    expect(state().users.find((u) => u.id === "u_me")).toMatchObject({ name: "Ali H.", handle: "alih" });
  });

  it("inviteMember adds a person with a name from their email", () => {
    actions.inviteMember("zara.ahmed@acme.dev", "admin");
    expect(state().users.at(-1)).toMatchObject({ name: "Zara Ahmed", handle: "zara-ahmed", role: "admin" });
  });

  it("changeMemberRole updates a member's role", () => {
    actions.changeMemberRole("u_omar", "admin");
    expect(state().users.find((u) => u.id === "u_omar")?.role).toBe("admin");
  });

  it("addCredential stores only a masked key; removeCredential deletes it", () => {
    actions.addCredential({ provider: "Mistral", label: "My key", owner: "user", key: "mst-1234567890abcd" });
    const key = state().credentials.at(-1)!;
    expect(key.maskedKey).toBe("mst-…abcd");
    expect(JSON.stringify(key)).not.toContain("1234567890");

    actions.removeCredential(key.id);
    expect(state().credentials.some((k) => k.id === key.id)).toBe(false);
  });

  it("connectApp and disconnectApp manage connections", () => {
    actions.connectApp("mcp", "https://mcp.acme.dev/sse");
    const connection = state().connections.at(-1)!;
    expect(connection).toMatchObject({ connectorId: "mcp", account: "https://mcp.acme.dev/sse", status: "connected" });

    actions.disconnectApp(connection.id);
    expect(state().connections.some((c) => c.id === connection.id)).toBe(false);
  });

  it("reset cancels a bot reply that's still on its way", () => {
    vi.useFakeTimers();
    actions.sendMessage("t_sales", "Hi");
    actions.reset();
    const before = messagesIn("t_sales").length;

    finishBotReply();
    expect(messagesIn("t_sales")).toHaveLength(before);
  });

  it("reset brings back the original mock data", () => {
    actions.deleteMemory("mem_1");
    actions.reset();
    expect(state().memories.some((m) => m.id === "mem_1")).toBe(true);
  });
});
