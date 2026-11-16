import { act, fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot as state } from "@/data/store";
import { renderUI } from "@/test/render";
import { RunWaitingNotices } from "./run-waiting-notice";

/** The Chief demo: Chief hands two Tasks to @sales and @inbox, then waits for them. */
function askChiefToPlan() {
  vi.useFakeTimers();
  actions.sendMessage("t_chief", "Plan the launch for next week");
  act(() => vi.advanceTimersByTime(700)); // Chief has handed off
}

describe("RunWaitingNotices", () => {
  it("says who the bot is waiting for, and drops each teammate once they've finished", () => {
    askChiefToPlan();
    renderUI(<RunWaitingNotices threadId="t_chief" />);
    expect(screen.getByRole("status")).toHaveTextContent("Chief is waiting for @sales and @inbox");

    // Sales works and replies; Inbox is still to come.
    act(() => vi.advanceTimersByTime(700 + 600 + 60 * 40));
    expect(screen.getByRole("status")).toHaveTextContent("Chief is waiting for @inbox");
  });

  it("shows nothing when no bot is waiting", () => {
    renderUI(<RunWaitingNotices threadId="t_chief" />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("Stop ends the wait and cancels the tasks still open", async () => {
    askChiefToPlan();
    renderUI(<RunWaitingNotices threadId="t_chief" />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Stop Chief" })));

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    const cards = state().messages.flatMap((m) => m.parts.filter((p) => p.type === "handoff" && p.taskId.startsWith("mock-task-")));
    expect(cards.map((p) => p.type === "handoff" && p.status)).toEqual(["cancelled", "cancelled"]);
  });
});
