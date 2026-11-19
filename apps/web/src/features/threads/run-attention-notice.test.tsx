import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot as state } from "@/data/store";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { renderUI } from "@/test/render";
import { RunAttentionNotices } from "./run-attention-notice";

const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (message: string) => toastError(message) } }));

/** The chat's stream: these tests don't need its events. */
class QuietEventSource {
  addEventListener() {}
  close() {}
}

const stuck = {
  id: "r1", botId: "b1", threadId: "t1", triggerMessageId: "m1", replyMessageId: null, status: "needs_attention", stepsUsed: 1,
  maxSteps: 10, maxSeconds: 300, createdAt: "2026-11-12T09:00:00Z", startedAt: "2026-11-12T09:00:01Z", finishedAt: null,
  error: "flaky.send may have been done: it failed partway, and we can't tell whether it finished. Check before trying again.",
};

describe("RunAttentionNotices on the API", () => {
  const api = withFakeApi();

  beforeEach(async () => {
    toastError.mockClear();
    vi.stubGlobal("EventSource", QuietEventSource);
    api.routes["GET /api/v1/orgs/o1/threads/t1/runs?active=true"] = { status: 200, body: { runs: [stuck], lastEventId: 7, replayFrom: 7 } };
    api.routes["GET /api/v1/orgs/o1/threads/t1/messages?limit=50"] = { status: 200, body: [] };
    await signInOnApi();
    actions.openThread("t1");
    await vi.waitFor(() => expect(state().runs[0]?.status).toBe("needs_attention"));
  });

  it("asks a person what happened, next to Stop", () => {
    renderUI(<RunAttentionNotices threadId="t1" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Scout needs a person to check");
    expect(screen.getByText(stuck.error)).toBeInTheDocument();
    for (const name of ["It was done", "It wasn't done", "Stop"]) expect(screen.getByRole("button", { name })).toBeEnabled();
  });

  it("sends the answer with every button off until it's taken, then the bot carries on", async () => {
    let answer = () => {};
    const taken = new Promise<void>((resolve) => (answer = resolve));
    const fetchNow = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (url, init) => {
      if (String(url).endsWith("/runs/r1/resolve")) await taken;
      return fetchNow(url, init);
    });
    api.routes["POST /api/v1/orgs/o1/runs/r1/resolve"] = { status: 200, body: stuck };
    const { user } = renderUI(<RunAttentionNotices threadId="t1" />);

    await user.click(screen.getByRole("button", { name: "It was done" }));

    // The one sending shows a spinner (its name gains "Loading").
    for (const name of [/It was done/, /It wasn't done/, /Stop/]) expect(screen.getByRole("button", { name })).toBeDisabled();
    answer();
    await vi.waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(api.sent.find((r) => r.key === "POST /api/v1/orgs/o1/runs/r1/resolve")?.body).toEqual({ outcome: "done" });
    expect(toastError).not.toHaveBeenCalled();
  });

  it("shows why in a toast when the answer isn't taken, and keeps the notice", async () => {
    api.routes["POST /api/v1/orgs/o1/runs/r1/resolve"] = { status: 409, body: { detail: "This run isn't waiting for anyone to check on it." } };
    const { user } = renderUI(<RunAttentionNotices threadId="t1" />);

    await user.click(screen.getByRole("button", { name: "It wasn't done" }));

    await vi.waitFor(() => expect(toastError).toHaveBeenCalledWith("This run isn't waiting for anyone to check on it."));
    expect(api.sent.find((r) => r.key === "POST /api/v1/orgs/o1/runs/r1/resolve")?.body).toEqual({ outcome: "not_done" });
    expect(screen.getByRole("button", { name: "It wasn't done" })).toBeEnabled();
  });
});
