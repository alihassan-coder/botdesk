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

describe("decideApproval (mock)", () => {
  it("records the decision and who made it", async () => {
    await expect(actions.decideApproval("a_1", "approve")).resolves.toEqual({ ok: true });
    const approval = state().approvals.find((a) => a.id === "a_1");
    expect(approval?.status).toBe("approved");
    expect(approval?.decidedBy).toBe("u_me");
    expect(approval?.finalArgs).toEqual(approval?.args);
  });

  it("keeps the bot's status in step with what's still waiting", async () => {
    await actions.decideApproval("a_1", "approve");
    expect(state().bots.find((b) => b.id === "b_inbox")?.statusText).toBe("1 waiting for you");

    await actions.decideApproval("a_2", "deny");
    const inbox = state().bots.find((b) => b.id === "b_inbox");
    expect(inbox?.status).toBe("idle");
    expect(inbox?.statusText).toBe("All caught up");
  });

  it("has the bot confirm in the thread", async () => {
    vi.useFakeTimers();
    await actions.decideApproval("a_2", "deny");
    vi.advanceTimersByTime(1_000);
    expect(lastMessageIn("t_inbox").parts[0]).toEqual({
      type: "text",
      text: "Okay, I won't go ahead with “Decline vendor demo (Initech)”.",
    });
  });

  it("approving changed arguments marks it edited and shows your version", async () => {
    const edited = { to: "vicky@globex.com", subject: "Re: Thursday call", body: "Thursday works. Best, Ali" };
    await actions.decideApproval("a_1", "approve", edited);
    const approval = state().approvals.find((a) => a.id === "a_1");
    expect(approval).toMatchObject({ status: "edited", finalArgs: edited });
    expect(approval?.preview).toContainEqual({ label: "Body", value: "Thursday works. Best, Ali" });
  });

  it("approving the same arguments is a plain approval", async () => {
    const args = state().approvals.find((a) => a.id === "a_2")!.args!;
    await actions.decideApproval("a_2", "approve", { ...args });
    expect(state().approvals.find((a) => a.id === "a_2")?.status).toBe("approved");
  });

  it("a decided approval can't be decided again", async () => {
    await actions.decideApproval("a_4", "deny");
    expect(state().approvals.find((a) => a.id === "a_4")?.status).toBe("approved");
  });
});

describe("createGroup", () => {
  it("starts a group with you, the people and the bots you picked, at the top of your chats", async () => {
    const result = await actions.createGroup({ title: "  Hiring  ", botIds: ["b_talent", "b_chief"], userIds: ["u_sara"] });
    expect(result).toEqual({ ok: true, threadId: expect.any(String) });

    const { threadId } = result as { threadId: string };
    expect(state().threads[0]).toMatchObject({
      id: threadId, kind: "group", title: "Hiring", unread: 0,
      participants: [
        { type: "user", id: "u_me" },
        { type: "user", id: "u_sara" },
        { type: "bot", id: "b_talent" },
        { type: "bot", id: "b_chief" },
      ],
    });
  });

  it("adds you once, even if you're picked too", async () => {
    const { threadId } = (await actions.createGroup({ title: "Solo", botIds: ["b_chief"], userIds: ["u_me"] })) as { threadId: string };
    const people = state().threads.find((t) => t.id === threadId)!.participants.filter((p) => p.type === "user");
    expect(people).toEqual([{ type: "user", id: "u_me" }]);
  });

  it("needs a name and at least one bot", async () => {
    const before = state().threads.length;
    await expect(actions.createGroup({ title: " ", botIds: ["b_chief"], userIds: [] })).resolves.toEqual({ ok: false, error: "Give the group a name." });
    await expect(actions.createGroup({ title: "No bots", botIds: [], userIds: ["u_sara"] })).resolves.toEqual({ ok: false, error: "Pick at least one bot." });
    expect(state().threads).toHaveLength(before);
  });

  it("in the new group, the bot you @mention replies", async () => {
    vi.useFakeTimers();
    const { threadId } = (await actions.createGroup({ title: "Ops", botIds: ["b_chief", "b_bugs"], userIds: [] })) as { threadId: string };
    actions.sendMessage(threadId, "@bugs is staging up?");
    finishBotReply();
    expect(lastMessageIn(threadId).author).toEqual({ type: "bot", id: "b_bugs" });
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

  it("createBotFromTemplate hires the bot and opens a chat where it speaks first", async () => {
    const { threadId } = (await actions.createBotFromTemplate("tpl_inbox")) as { threadId: string };
    const thread = state().threads.find((t) => t.id === threadId);

    expect(thread?.kind).toBe("dm");
    expect(state().bots.find((b) => b.id === thread?.botId)?.name).toBe("Inbox Zero");
    expect(messagesIn(threadId!)[0].author.type).toBe("bot");
  });

  it("createBot builds a bot from your choices, with a unique handle", async () => {
    const { threadId } = (await actions.createBot({
      name: "Chief", role: "Second chief", description: "", avatarColor: "rose", instructions: "Be brief.",
      modelId: "m_gpt", securityLevel: "read-only", computerMode: "none", monthlyBudgetUsd: 10,
    })) as { threadId: string };
    const bot = state().bots.find((b) => b.id === state().threads.find((t) => t.id === threadId)?.botId);

    expect(bot).toMatchObject({ handle: "chief-2", modelId: "m_gpt", securityLevel: "read-only", spentThisMonthUsd: 0, status: "idle" });
    expect(messagesIn(threadId)[0].parts[0]).toMatchObject({ type: "text", text: expect.stringContaining("Second chief") });
  });

  it("editBot changes a bot; removeBot takes it, its chat and its approvals away", async () => {
    await expect(actions.editBot("b_inbox", { name: "Inbox Pro" })).resolves.toEqual({ ok: true });
    expect(state().bots.find((b) => b.id === "b_inbox")?.name).toBe("Inbox Pro");

    await expect(actions.removeBot("b_inbox")).resolves.toEqual({ ok: true });
    expect(state().bots.some((b) => b.id === "b_inbox")).toBe(false);
    expect(state().threads.some((t) => t.botId === "b_inbox")).toBe(false);
    expect(state().approvals.some((a) => a.botId === "b_inbox")).toBe(false);
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
