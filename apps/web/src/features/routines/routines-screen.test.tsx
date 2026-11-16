import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { CreateRoutineScreen } from "./create-routine-screen";
import { RoutineForm } from "./routine-form";
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

  function signInAs(role: "owner" | "member") {
    api.routes["GET /api/v1/orgs/o1/members"] = { status: 200, body: [] };
    api.routes["POST /api/v1/auth/sign-in"] = {
      status: 200,
      body: { user: { id: "u1", name: "Zara", email: "zara@example.com", handle: "zara" }, organizations: [{ id: "o1", name: "Team", slug: "team", role, defaultSecurityLevel: "ask-before-acting" }] },
    };
  }

  it("a teammate's routine whose instructions the API hides shows its schedule, and says what it can't show", async () => {
    signInAs("member");
    await signIn([{ ...apiRoutine, createdBy: "u2", instructions: null }]);
    renderUI(<RoutinesScreen />);
    const card = screen.getByRole("article", { name: "Morning digest" });
    expect(card).toHaveTextContent("Weekdays at 7:30 AM");
    expect(card).toHaveTextContent("Only its creator, owners and admins see what it does.");
  });

  it("an owner can switch a member's routine off or delete it, but not edit it or run it as them", async () => {
    signInAs("owner");
    await signIn([{ ...apiRoutine, createdBy: "u2" }]);
    renderUI(<RoutinesScreen />);
    expect(screen.getByRole("switch", { name: "Run Morning digest" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Delete Morning digest" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run now" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Edit Morning digest" })).not.toBeInTheDocument();
  });

  it("a custom line keeps a list of minutes, and a bad one says so on the field itself", async () => {
    await signIn([{ ...apiRoutine, cron: "0,30 9 * * *" }]);
    const [routine] = getStoreSnapshot().routines;
    const { user } = renderUI(<RoutineForm routine={routine} />);
    const line = screen.getByRole("textbox", { name: "Cron line" });
    expect(line).toHaveValue("0,30 9 * * *");
    expect(screen.getByText("Every day at 9 AM and 9:30 AM")).toBeInTheDocument();
    await user.clear(line);
    await user.type(line, "0 9");
    await user.click(screen.getByRole("button", { name: "Save routine" }));
    expect(line).toHaveAttribute("aria-invalid", "true");
    expect(line).toHaveAccessibleDescription("A cron line has 5 parts: minute hour day month weekday.");
    expect(api.sent.some((r) => r.key.startsWith("PATCH"))).toBe(false);
  });

  it("a cleared time is an error on the time field, not a schedule of NaN", async () => {
    await signIn([apiRoutine]);
    const [routine] = getStoreSnapshot().routines;
    const { user } = renderUI(<RoutineForm routine={routine} />);
    const time = screen.getByLabelText("Time");
    await user.clear(time);
    expect(screen.getByText("Weekdays (pick a time)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save routine" }));
    expect(time).toHaveAttribute("aria-invalid", "true");
    expect(time).toHaveAccessibleDescription("Pick a time.");
    expect(api.sent.some((r) => r.key.startsWith("PATCH"))).toBe(false);
  });

  it("the name's error is tied to the name field", async () => {
    await signIn([]);
    const { user } = renderUI(<CreateRoutineScreen />);
    await user.click(screen.getByRole("button", { name: "Save routine" }));
    expect(screen.getByLabelText("Name")).toHaveAccessibleDescription("Give the routine a name.");
    expect(screen.getByLabelText("What to do")).toHaveAccessibleDescription(
      "The bot reads this each time, in your chat with it, and replies there. Say what the bot should do.",
    );
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
