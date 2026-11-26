import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Message } from "@/data/types";
import { FollowOnSend } from "./follow-on-send";

// The scroller's own scrolling needs a layout engine; here it's a spy, and the glide is checked on a stub box.
const scroller = vi.hoisted(() => ({ scrollToEnd: vi.fn() }));
vi.mock("@/components/ui/message-scroller", () => ({ useMessageScroller: () => scroller }));

const message = (id: string, author: Message["author"]): Message => ({
  id, threadId: "t_talent", author, parts: [{ type: "text", text: id }], createdAt: "2026-11-26T10:00:00Z",
});
const mine = (id: string) => message(id, { type: "user", id: "u_me" });
const scouts = (id: string) => message(id, { type: "bot", id: "b_talent" });

/** A chat scrolled to the top of 3000 px, 500 px seen. */
function scrolledUp() {
  const box = document.createElement("div");
  let top = 0;
  Object.defineProperty(box, "scrollTop", { get: () => top, set: (v: number) => (top = v) });
  Object.defineProperty(box, "clientHeight", { value: 500 });
  Object.defineProperty(box, "scrollHeight", { value: 3000 });
  return { current: box };
}

describe("FollowOnSend", () => {
  let frames: FrameRequestCallback[] = [];
  const frame = (now: number) => frames.splice(0).forEach((run) => run(now));
  const matchMedia = window.matchMedia;

  beforeEach(() => {
    frames = [];
    scroller.scrollToEnd.mockClear();
    vi.stubGlobal("requestAnimationFrame", (run: FrameRequestCallback) => frames.push(run));
    vi.stubGlobal("cancelAnimationFrame", () => (frames = []));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    window.matchMedia = matchMedia;
  });

  it("glides down to the message you just sent, even from far up, then hands back to the scroller", () => {
    const viewport = scrolledUp();
    const { rerender } = render(<FollowOnSend viewport={viewport} messages={[scouts("m1")]} />);
    expect(viewport.current.scrollTop).toBe(0); // opening the chat isn't sending

    rerender(<FollowOnSend viewport={viewport} messages={[scouts("m1"), mine("m2")]} />);
    // From far up it jumps to a screen above the end, then glides the rest.
    expect(viewport.current.scrollTop).toBe(2000);
    frame(0);
    frame(160);
    expect(viewport.current.scrollTop).toBeGreaterThan(2000);
    expect(viewport.current.scrollTop).toBeLessThan(2500);
    frame(400);
    expect(viewport.current.scrollTop).toBe(2500);
    expect(scroller.scrollToEnd).toHaveBeenCalledWith({ behavior: "instant" });
  });

  it("jumps instead of gliding for people who asked for less motion", () => {
    window.matchMedia = ((query: string) => ({ ...matchMedia(query), matches: query.includes("reduce") })) as typeof window.matchMedia;
    const viewport = scrolledUp();
    const { rerender } = render(<FollowOnSend viewport={viewport} messages={[scouts("m1")]} />);
    rerender(<FollowOnSend viewport={viewport} messages={[scouts("m1"), mine("m2")]} />);
    expect(scroller.scrollToEnd).toHaveBeenCalledWith({ behavior: "instant" });
    expect(frames).toHaveLength(0);
  });

  it("leaves you where you are for a reply, older messages, or your message being saved", () => {
    const viewport = scrolledUp();
    const { rerender } = render(<FollowOnSend viewport={viewport} messages={[mine("local-1")]} />);
    rerender(<FollowOnSend viewport={viewport} messages={[mine("m2")]} />); // saved: same message, new id
    rerender(<FollowOnSend viewport={viewport} messages={[mine("m2"), scouts("m3")]} />);
    rerender(<FollowOnSend viewport={viewport} messages={[scouts("m0"), mine("m2"), scouts("m3")]} />);
    expect(viewport.current.scrollTop).toBe(0);
    expect(scroller.scrollToEnd).not.toHaveBeenCalled();
  });
});
