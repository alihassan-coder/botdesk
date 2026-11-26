/** A strong ease-out: fast at first, so the scroll answers at once, then settling gently. */
export const easeOut = (t: number) => 1 - (1 - t) ** 4;

/**
 * Where a glide to the end starts. From more than a screen and a half up, it jumps to one screen
 * above the end first: gliding through hundreds of messages is a blur and makes the browser draw them all.
 */
export function glideStart(scrollTop: number, end: number, viewportHeight: number): number {
  return end - scrollTop > viewportHeight * 1.5 ? end - viewportHeight : scrollTop;
}

/** What a person does that means they want to scroll themselves, so a glide stops. */
const TAKE_OVER = ["wheel", "touchstart", "pointerdown", "keydown"] as const;

/**
 * Scrolls `viewport` to its end over `duration` ms, then calls `done`. The end is read again each
 * frame, so a reply that starts meanwhile is followed too. Stops (without `done`) when the person
 * scrolls, presses or types in it, or when the returned function is called.
 */
export function glideToEnd(viewport: HTMLElement, done: () => void, duration = 320): () => void {
  const end = () => Math.max(0, viewport.scrollHeight - viewport.clientHeight);
  const from = glideStart(viewport.scrollTop, end(), viewport.clientHeight);
  let started: number | undefined;
  let frame = 0;

  const stop = () => {
    cancelAnimationFrame(frame);
    TAKE_OVER.forEach((type) => viewport.removeEventListener(type, stop));
  };
  const step = (now: number) => {
    started ??= now;
    const t = Math.min(1, (now - started) / duration);
    // Only ever down: if something else already scrolled further (the scroller jumping to a new
    // reply), the glide doesn't pull the view back up.
    viewport.scrollTop = Math.max(viewport.scrollTop, from + (end() - from) * easeOut(t));
    if (t < 1) frame = requestAnimationFrame(step);
    else {
      stop();
      done();
    }
  };

  TAKE_OVER.forEach((type) => viewport.addEventListener(type, stop, { passive: true }));
  viewport.scrollTop = from;
  frame = requestAnimationFrame(step);
  return stop;
}

/** People who asked for less motion get an instant scroll instead. */
export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
