import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot as state } from "@/data/store";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { renderUI } from "@/test/render";
import { Composer } from "./composer";

const toast = vi.fn();
vi.mock("sonner", () => ({ toast: Object.assign((message: string) => toast(message), { error: (message: string) => toast(message) }) }));

describe("Composer: drafts and history (demo)", () => {
  const sales = () => state().threads.find((t) => t.id === "t_sales")!;
  afterEach(() => localStorage.clear());

  it("keeps what you were writing when you leave the chat and come back", async () => {
    const first = renderUI(<Composer thread={sales()} />);
    await first.user.type(screen.getByRole("textbox", { name: "Message Sales Outbound" }), "Half a thought");
    await vi.waitFor(() => expect(localStorage.getItem("botdesk.draft.t_sales")).toBe("Half a thought"));
    first.unmount();

    renderUI(<Composer thread={sales()} />);
    expect(screen.getByRole("textbox", { name: "Message Sales Outbound" })).toHaveValue("Half a thought");
  });

  it("sending clears the draft", async () => {
    const { user } = renderUI(<Composer thread={sales()} />);
    await user.type(screen.getByRole("textbox", { name: "Message Sales Outbound" }), "Ship it{Enter}");
    expect(localStorage.getItem("botdesk.draft.t_sales")).toBeNull();
  });

  it("Up brings back what you sent, Down goes back to the empty box", async () => {
    const { user } = renderUI(<Composer thread={sales()} />);
    const box = screen.getByRole("textbox", { name: "Message Sales Outbound" });
    await user.type(box, "First request{Enter}");
    await user.type(box, "Second request{Enter}");

    await user.keyboard("{ArrowUp}");
    expect(box).toHaveValue("Second request");
    await user.keyboard("{ArrowUp}");
    expect(box).toHaveValue("First request");
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(box).toHaveValue("");
  });

  it("Up doesn't take over a box you're writing in", async () => {
    const { user } = renderUI(<Composer thread={sales()} />);
    const box = screen.getByRole("textbox", { name: "Message Sales Outbound" });
    await user.type(box, "Sent before{Enter}");
    await user.type(box, "new words{ArrowUp}");
    expect(box).toHaveValue("new words");
  });
});

/** The chat's stream: these tests don't need its events. */
class QuietEventSource {
  addEventListener() {}
  close() {}
}

const working = {
  id: "r1", botId: "b1", threadId: "t1", triggerMessageId: "m1", replyMessageId: null, status: "running", stepsUsed: 2,
  maxSteps: 25, maxSeconds: 900, createdAt: "2026-11-27T09:00:00Z", startedAt: "2026-11-27T09:00:01Z", finishedAt: null, error: null,
};
const sentMessage = {
  id: "m2", threadId: "t1", author: { type: "user", id: "u1" }, parts: [{ type: "text", text: "x" }], status: "complete",
  createdAt: "2026-11-27T09:01:00Z", runIds: [],
};

describe("Composer: while a bot is working (API)", () => {
  const api = withFakeApi();
  const dm = () => state().threads.find((t) => t.id === "t1")!;
  const box = () => screen.getByRole("textbox", { name: "Message Scout" });
  const posted = () => api.sent.filter((r) => r.key === "POST /api/v1/orgs/o1/threads/t1/messages").map((r) => r.body);

  beforeEach(async () => {
    toast.mockClear();
    vi.stubGlobal("EventSource", QuietEventSource);
    api.routes["GET /api/v1/orgs/o1/threads/t1/runs?active=true"] = { status: 200, body: { runs: [working], lastEventId: 1, replayFrom: 1 } };
    api.routes["GET /api/v1/orgs/o1/threads/t1/messages?limit=50"] = { status: 200, body: [] };
    api.routes["POST /api/v1/orgs/o1/threads/t1/messages"] = { status: 201, body: sentMessage };
    api.routes["GET /api/v1/orgs/o1/voice"] = { status: 200, body: { available: false, provider: null, model: null, message: "Voice needs an OpenAI or Groq key." } };
    await signInOnApi();
    actions.openThread("t1");
    await vi.waitFor(() => expect(state().runs.some((r) => r.threadId === "t1")).toBe(true));
  });

  it("with nothing typed there's only Stop; typing offers Send now", async () => {
    const { user } = renderUI(<Composer thread={dm()} />);
    expect(screen.getByRole("button", { name: "Stop replying" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /send/i })).not.toBeInTheDocument();
    await user.type(box(), "Use the GitHub tools");
    expect(screen.getByRole("button", { name: "Send now" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop replying" })).toBeInTheDocument();
  });

  it("Enter sends now: the bot reads it at its next step", async () => {
    const { user } = renderUI(<Composer thread={dm()} />);
    await user.type(box(), "Use the GitHub tools{Enter}");
    await vi.waitFor(() => expect(posted()).toEqual([{ text: "Use the GitHub tools", delivery: "now" }]));
  });

  it("Alt+Enter, or Queue in the menu, waits for the bot to finish", async () => {
    const { user } = renderUI(<Composer thread={dm()} />);
    await user.type(box(), "Then write the README{Alt>}{Enter}{/Alt}");
    await vi.waitFor(() => expect(posted()).toEqual([{ text: "Then write the README" }]));
    expect(toast).toHaveBeenCalledWith("Queued. Scout answers it after it finishes.");

    await user.type(box(), "And a changelog");
    await user.click(screen.getByRole("button", { name: "More ways to send" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText("Scout reads it at its next step and carries on.")).toBeInTheDocument();
    await user.click(within(menu).getByRole("menuitem", { name: /Queue/ }));
    await vi.waitFor(() => expect(posted()).toHaveLength(2));
    expect(posted()[1]).toEqual({ text: "And a changelog" });
  });

  it("the microphone says how to turn voice on when no key reaches a speech model", async () => {
    const { user } = renderUI(<Composer thread={dm()} />);
    await vi.waitFor(() => expect(state().voice.status).toBe("ready"));
    await user.click(screen.getByRole("button", { name: "Talk instead of typing" }));
    expect(toast).toHaveBeenCalledWith("Voice needs an OpenAI or Groq key.");
  });
});
