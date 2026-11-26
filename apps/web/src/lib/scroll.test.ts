import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { easeOut, glideStart, glideToEnd } from "./scroll";

describe("easeOut", () => {
  it("starts fast and lands exactly", () => {
    expect(easeOut(0)).toBe(0);
    expect(easeOut(1)).toBe(1);
    expect(easeOut(0.25)).toBeGreaterThan(0.6);
  });
});

describe("glideStart", () => {
  it("glides from where you are when the end is near", () => {
    expect(glideStart(900, 1500, 500)).toBe(900);
  });

  it("jumps to a screen above the end first when it's far", () => {
    expect(glideStart(0, 1500, 500)).toBe(1000);
  });
});

/** A scrolling box with a height jsdom doesn't have: `content` tall, 500 px seen. */
function scrollBox(content: number) {
  const box = document.createElement("div");
  let top = 0;
  Object.defineProperty(box, "scrollTop", { get: () => top, set: (v: number) => (top = v) });
  Object.defineProperty(box, "clientHeight", { value: 500 });
  Object.defineProperty(box, "scrollHeight", { get: () => content, configurable: true });
  return { box, grow: (by: number) => (content += by) };
}

describe("glideToEnd", () => {
  let frames: FrameRequestCallback[] = [];
  const frame = (now: number) => frames.splice(0).forEach((run) => run(now));

  beforeEach(() => {
    frames = [];
    vi.stubGlobal("requestAnimationFrame", (run: FrameRequestCallback) => frames.push(run));
    vi.stubGlobal("cancelAnimationFrame", () => (frames = []));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("moves down a little each frame and lands on the end, then says so", () => {
    const { box } = scrollBox(1500);
    box.scrollTop = 600;
    const done = vi.fn();
    glideToEnd(box, done, 300);

    frame(0);
    frame(100);
    expect(box.scrollTop).toBeGreaterThan(600);
    expect(box.scrollTop).toBeLessThan(1000);
    expect(done).not.toHaveBeenCalled();
    frame(300);
    expect(box.scrollTop).toBe(1000);
    expect(done).toHaveBeenCalledOnce();
  });

  it("follows the end when it moves meanwhile (a reply starts)", () => {
    const { box, grow } = scrollBox(1500);
    box.scrollTop = 600;
    glideToEnd(box, () => {}, 300);
    frame(0);
    grow(200);
    frame(300);
    expect(box.scrollTop).toBe(1200);
  });

  it("stops when the person scrolls themselves", () => {
    const { box } = scrollBox(1500);
    box.scrollTop = 600;
    const done = vi.fn();
    glideToEnd(box, done, 300);
    frame(0);
    box.dispatchEvent(new WheelEvent("wheel"));
    frame(300);
    expect(box.scrollTop).toBe(600);
    expect(done).not.toHaveBeenCalled();
  });

  it("never pulls the view back up", () => {
    const { box } = scrollBox(1500);
    box.scrollTop = 600;
    glideToEnd(box, () => {}, 300);
    frame(0);
    box.scrollTop = 1000; // something else jumped to the end
    frame(50);
    expect(box.scrollTop).toBe(1000);
  });
});
