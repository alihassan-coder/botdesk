import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { actions } from "@/data/store";
import { LoadOlderMessages } from "./load-older-messages";

/** jsdom has no IntersectionObserver: this one reports only when a test says the top came near. */
class FakeObserver {
  static all: FakeObserver[] = [];
  disconnected = false;
  constructor(
    readonly report: (entries: Pick<IntersectionObserverEntry, "isIntersecting">[]) => void,
    readonly options: IntersectionObserverInit,
  ) {
    FakeObserver.all.push(this);
  }
  observe() {}
  unobserve() {}
  takeRecords() {
    return [];
  }
  disconnect() {
    this.disconnected = true;
  }
}

const current = () => FakeObserver.all.filter((o) => !o.disconnected).at(-1)!;
const nearTop = (seen = true) => act(() => current().report([{ isIntersecting: seen }]));

describe("LoadOlderMessages", () => {
  const root = document.createElement("div");
  const scrollRoot = { current: root };
  let land: () => void;

  beforeEach(() => {
    FakeObserver.all = [];
    vi.stubGlobal("IntersectionObserver", FakeObserver);
    vi.spyOn(actions, "loadOlderMessages").mockImplementation(
      () => new Promise((resolve) => (land = () => resolve({ ok: true }))),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads the page before when you scroll up near the top, once at a time", async () => {
    render(<LoadOlderMessages threadId="t1" oldestId="m1" scrollRoot={scrollRoot} />);
    expect(current().options).toMatchObject({ root, rootMargin: "100% 0px 0px 0px" });

    nearTop(false);
    expect(actions.loadOlderMessages).not.toHaveBeenCalled();

    nearTop();
    nearTop();
    expect(actions.loadOlderMessages).toHaveBeenCalledTimes(1);
    expect(actions.loadOlderMessages).toHaveBeenCalledWith("t1");
    expect(screen.getByRole("button", { name: "Loading earlier messages…" })).toBeDisabled();

    await act(async () => land());
    expect(screen.getByRole("button", { name: "Show earlier messages" })).toBeEnabled();
  });

  it("checks the top again once a page has landed, so a short page doesn't stop it", async () => {
    const { rerender } = render(<LoadOlderMessages threadId="t1" oldestId="m1" scrollRoot={scrollRoot} />);
    nearTop();
    await act(async () => land());
    const first = current();

    rerender(<LoadOlderMessages threadId="t1" oldestId="m0" scrollRoot={scrollRoot} />);
    expect(first.disconnected).toBe(true);
    nearTop();
    expect(actions.loadOlderMessages).toHaveBeenCalledTimes(2);
  });

  it("keeps the button for anyone who'd rather press it", async () => {
    const user = userEvent.setup();
    render(<LoadOlderMessages threadId="t1" oldestId="m1" scrollRoot={scrollRoot} />);
    await user.click(screen.getByRole("button", { name: "Show earlier messages" }));
    expect(actions.loadOlderMessages).toHaveBeenCalledTimes(1);
    // Coming near the top meanwhile doesn't ask again.
    nearTop();
    expect(actions.loadOlderMessages).toHaveBeenCalledTimes(1);
  });
});
