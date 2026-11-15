import { describe, expect, it, vi } from "vitest";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { actions, getStoreSnapshot as state } from "./store";

/* Routines on the API: loaded with the org, created with a cron line and time zone, switched, run now, removed. */

const api = withFakeApi();

const apiRoutine = {
  id: "r1", botId: "b1", createdBy: "u1", name: "Morning digest", instructions: "Sum up yesterday.",
  cron: "30 7 * * 1-5", timezone: "Asia/Karachi", enabled: true, securityLevel: null, disabledReason: null,
  lastRunAt: "2026-11-14T02:30:00Z", nextRunAt: "2026-11-16T02:30:00Z", lastResult: "succeeded", createdAt: "2026-11-12T08:00:00Z",
};

async function signedInWith(routines: unknown[]) {
  api.routes["GET /api/v1/orgs/o1/routines"] = { status: 200, body: routines };
  await signInOnApi();
  await vi.waitFor(() => expect(state().routinesLoading).toBe(false));
}

describe("routines, on the API", () => {
  it("come with the org, their schedule in words", async () => {
    await signedInWith([apiRoutine]);
    expect(state().routines).toEqual([
      expect.objectContaining({
        id: "r1", botId: "b1", description: "Sum up yesterday.", schedule: "Weekdays at 7:30 AM", timezone: "Asia/Karachi",
        nextRunAt: "2026-11-16T02:30:00Z", lastOutcome: "success", enabled: true, steps: [],
      }),
    ]);
  });

  it("createRoutine sends what to do, the cron line and the time zone, and keeps what the API saved", async () => {
    await signedInWith([]);
    api.routes["POST /api/v1/orgs/o1/routines"] = { status: 201, body: apiRoutine };
    const result = await actions.createRoutine({
      botId: "b1", name: "Morning digest", description: "Sum up yesterday.", schedule: "Weekdays at 7:30 AM", steps: [],
      enabled: true, cron: "30 7 * * 1-5", timezone: "Asia/Karachi",
    });
    expect(result).toEqual({ ok: true, routineId: "r1" });
    expect(api.sent.at(-1)).toEqual({
      key: "POST /api/v1/orgs/o1/routines",
      body: { botId: "b1", name: "Morning digest", instructions: "Sum up yesterday.", enabled: true, cron: "30 7 * * 1-5", timezone: "Asia/Karachi" },
    });
    expect(state().routines.map((r) => r.id)).toEqual(["r1"]);
  });

  it("a refused routine isn't saved and says why", async () => {
    await signedInWith([]);
    api.routes["POST /api/v1/orgs/o1/routines"] = { status: 400, body: { detail: "Unknown time zone: Mars/Olympus." } };
    const result = await actions.createRoutine({
      botId: "b1", name: "X", description: "Y", schedule: "", steps: [], enabled: true, cron: "0 9 * * *", timezone: "Mars/Olympus",
    });
    expect(result).toEqual({ ok: false, error: "Unknown time zone: Mars/Olympus." });
    expect(state().routines).toEqual([]);
  });

  it("toggleRoutine switches it at once and keeps the API's answer, or puts it back", async () => {
    await signedInWith([apiRoutine]);
    api.routes["PATCH /api/v1/orgs/o1/routines/r1"] = { status: 200, body: { ...apiRoutine, enabled: false, nextRunAt: null } };
    await expect(actions.toggleRoutine("r1")).resolves.toEqual({ ok: true });
    expect(api.sent.at(-1)).toEqual({ key: "PATCH /api/v1/orgs/o1/routines/r1", body: { enabled: false } });
    expect(state().routines[0].enabled).toBe(false);
    expect(state().routines[0].nextRunAt).toBeUndefined();

    api.routes["PATCH /api/v1/orgs/o1/routines/r1"] = { status: 403, body: { detail: "Only the routine's creator, owners and admins can change it." } };
    await expect(actions.toggleRoutine("r1")).resolves.toMatchObject({ ok: false });
    expect(state().routines[0].enabled).toBe(false);
  });

  it("runRoutineNow asks the API, then shows the run going", async () => {
    await signedInWith([apiRoutine]);
    api.routes["POST /api/v1/orgs/o1/routines/r1/run-now"] = { status: 202, body: { runId: "run1", threadId: "t1" } };
    api.routes["GET /api/v1/orgs/o1/routines"] = { status: 200, body: [{ ...apiRoutine, lastResult: "queued" }] };
    await expect(actions.runRoutineNow("r1")).resolves.toEqual({ ok: true });
    expect(state().routines[0].lastOutcome).toBe("running");

    api.routes["POST /api/v1/orgs/o1/routines/r1/run-now"] = { status: 409, body: { detail: "This routine's last run is still going." } };
    await expect(actions.runRoutineNow("r1")).resolves.toEqual({ ok: false, error: "This routine's last run is still going." });
  });

  it("deleteRoutine removes it", async () => {
    await signedInWith([apiRoutine]);
    api.routes["DELETE /api/v1/orgs/o1/routines/r1"] = { status: 204 };
    await expect(actions.deleteRoutine("r1")).resolves.toEqual({ ok: true });
    expect(state().routines).toEqual([]);
  });

  it("a routine whose bot was removed stays, switched off, saying why", async () => {
    await signedInWith([apiRoutine]);
    api.routes["DELETE /api/v1/orgs/o1/bots/b1"] = { status: 204 };
    await actions.removeBot("b1");
    expect(state().routines[0]).toMatchObject({ botId: "", enabled: false, disabledReason: "Its bot was removed." });
  });
});
