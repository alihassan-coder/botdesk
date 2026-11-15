import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { CreateRoutineScreen } from "./create-routine-screen";
import { RoutinesScreen } from "./routines-screen";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, back: vi.fn() }) }));

describe("Routines in the demo", () => {
  it("lists the demo's routines and offers New routine", () => {
    renderUI(<RoutinesScreen />);
    expect(screen.getByText(/running\. A bot learns a routine/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New routine" })).toBeInTheDocument();
  });

  it("New routine shows the demo's form, with steps", () => {
    renderUI(<CreateRoutineScreen />);
    expect(screen.getByRole("button", { name: "Save routine" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add step" })).toBeInTheDocument();
  });
});

const apiRoutine = {
  id: "r1", botId: "b1", createdBy: "u1", name: "Morning digest", instructions: "Sum up yesterday's chats.",
  cron: "30 7 * * 1-5", timezone: "Asia/Karachi", enabled: true, securityLevel: null, disabledReason: null,
  lastRunAt: "2026-11-14T02:30:00Z", nextRunAt: "2026-11-16T02:30:00Z", lastResult: "succeeded", createdAt: "2026-11-12T08:00:00Z",
};

describe("Routines on the API", () => {
  const api = withFakeApi();

  async function signIn(routines: unknown[]) {
    api.routes["GET /api/v1/orgs/o1/routines"] = { status: 200, body: routines };
    await signInOnApi();
    await vi.waitFor(() => expect(getStoreSnapshot().routinesLoading).toBe(false));
  }

  it("lists each routine: bot, schedule in words with its time zone, next run and last result", async () => {
    await signIn([apiRoutine]);
    renderUI(<RoutinesScreen />);
    const card = screen.getByRole("article", { name: "Morning digest" });
    expect(card).toHaveTextContent("Weekdays at 7:30 AM");
    expect(card).toHaveTextContent("(Asia/Karachi)");
    expect(card).toHaveTextContent("Next: Mon, Nov 16, 7:30 AM");
    expect(card).toHaveTextContent("Run by Scout");
    expect(card).toHaveTextContent("Last run worked");
    expect(screen.getByRole("switch", { name: "Run Morning digest" })).toBeChecked();
  });

  it("the switch turns a routine off on the API", async () => {
    await signIn([apiRoutine]);
    api.routes["PATCH /api/v1/orgs/o1/routines/r1"] = { status: 200, body: { ...apiRoutine, enabled: false, nextRunAt: null } };
    const { user } = renderUI(<RoutinesScreen />);
    await user.click(screen.getByRole("switch", { name: "Run Morning digest" }));
    await waitFor(() => expect(screen.getByRole("switch", { name: "Run Morning digest" })).not.toBeChecked());
    expect(api.sent.at(-1)).toEqual({ key: "PATCH /api/v1/orgs/o1/routines/r1", body: { enabled: false } });
  });

  it("Run now starts it on the API", async () => {
    await signIn([apiRoutine]);
    api.routes["POST /api/v1/orgs/o1/routines/r1/run-now"] = { status: 202, body: { runId: "run1", threadId: "t1" } };
    const { user } = renderUI(<RoutinesScreen />);
    api.routes["GET /api/v1/orgs/o1/routines"] = { status: 200, body: [{ ...apiRoutine, lastResult: "running" }] };
    await user.click(screen.getByRole("button", { name: "Run now" }));
    await waitFor(() => expect(screen.getByRole("article", { name: "Morning digest" })).toHaveTextContent("Running now"));
    expect(api.sent.some((r) => r.key === "POST /api/v1/orgs/o1/routines/r1/run-now")).toBe(true);
  });

  it("a member sees a teammate's routine but can't change it", async () => {
    api.routes["GET /api/v1/orgs/o1/members"] = { status: 200, body: [] };
    api.routes["POST /api/v1/auth/sign-in"] = {
      status: 200,
      body: { user: { id: "u1", name: "Zara", email: "zara@example.com", handle: "zara" }, organizations: [{ id: "o1", name: "Team", slug: "team", role: "member", defaultSecurityLevel: "ask-before-acting" }] },
    };
    await signIn([{ ...apiRoutine, createdBy: "u2" }]);
    renderUI(<RoutinesScreen />);
    expect(screen.getByRole("switch", { name: "Run Morning digest" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Run now" })).not.toBeInTheDocument();
  });

  it("New routine saves what to do and a cron line in your time zone", async () => {
    await signIn([]);
    api.routes["POST /api/v1/orgs/o1/routines"] = { status: 201, body: apiRoutine };
    const { user } = renderUI(<CreateRoutineScreen />);
    expect(screen.queryByRole("button", { name: "Add step" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Name"), "Morning digest");
    await user.type(screen.getByLabelText("What to do"), "Sum up yesterday's chats.");
    await user.click(screen.getByRole("button", { name: "Save routine" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/routines"));
    const sent = api.sent.find((r) => r.key === "POST /api/v1/orgs/o1/routines");
    expect(sent?.body).toEqual({
      botId: "b1", name: "Morning digest", instructions: "Sum up yesterday's chats.", enabled: true,
      cron: "0 9 * * 1-5", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    });
  }, 15_000); // typing two fields with user-event is slow

  it("New routine asks for what to do before saving", async () => {
    await signIn([]);
    const { user } = renderUI(<CreateRoutineScreen />);
    await user.type(screen.getByLabelText("Name"), "Digest");
    await user.click(screen.getByRole("button", { name: "Save routine" }));
    expect(screen.getByText("Say what the bot should do.")).toBeInTheDocument();
    expect(api.sent.some((r) => r.key === "POST /api/v1/orgs/o1/routines")).toBe(false);
  });
});
