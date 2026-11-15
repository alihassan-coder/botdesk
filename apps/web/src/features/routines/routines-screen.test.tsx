import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { CreateRoutineScreen } from "./create-routine-screen";
import { RoutinesScreen } from "./routines-screen";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), back: vi.fn() }) }));

const COMING_SOON = "Bots can't run on a schedule yet. Routines arrive with the scheduler.";

describe("Routines in the demo", () => {
  it("lists the demo's routines and offers New routine", () => {
    renderUI(<RoutinesScreen />);
    expect(screen.getByText(/running\. A bot learns a routine/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New routine" })).toBeInTheDocument();
    expect(screen.queryByText(COMING_SOON)).not.toBeInTheDocument();
  });

  it("New routine shows the form", () => {
    renderUI(<CreateRoutineScreen />);
    expect(screen.getByRole("button", { name: "Save routine" })).toBeInTheDocument();
  });
});

describe("Routines on the API", () => {
  withFakeApi();

  it("says routines aren't here yet instead of a list that pretends to run", async () => {
    await signInOnApi();
    renderUI(<RoutinesScreen />);
    expect(screen.getByText(COMING_SOON)).toBeInTheDocument();
    expect(screen.queryByText(/running\./)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "New routine" })).not.toBeInTheDocument();
  });

  it("New routine says the same, with no form to fill in", async () => {
    await signInOnApi();
    renderUI(<CreateRoutineScreen />);
    expect(screen.getByText(COMING_SOON)).toBeInTheDocument();
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  });
});
