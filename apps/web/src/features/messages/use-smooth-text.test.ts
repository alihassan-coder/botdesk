import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { revealStep, useSmoothText } from "./use-smooth-text";

describe("revealStep", () => {
  it("shows an eighth of what's waiting each frame, at least one character", () => {
    expect(revealStep(0)).toBe(0);
    expect(revealStep(3)).toBe(1);
    expect(revealStep(80)).toBe(10);
    expect(revealStep(801)).toBe(101);
  });
});

describe("useSmoothText", () => {
  afterEach(() => vi.useRealTimers());

  it("eases a burst of words in while streaming, and catches up", () => {
    vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame"] });
    const { result, rerender } = renderHook(({ text }) => useSmoothText(text, true), { initialProps: { text: "" } });
    rerender({ text: "Hello there, this is a reply that arrived in one burst." });
    expect(result.current).toBe("");
    act(() => vi.advanceTimersToNextFrame());
    const first = result.current.length;
    expect(first).toBeGreaterThan(0);
    expect(first).toBeLessThan(55);
    act(() => {
      for (let i = 0; i < 60; i++) vi.advanceTimersToNextFrame();
    });
    expect(result.current).toBe("Hello there, this is a reply that arrived in one burst.");
  });

  it("shows the whole text at once when the reply is complete", () => {
    const { result } = renderHook(() => useSmoothText("All of it", false));
    expect(result.current).toBe("All of it");
  });
});
