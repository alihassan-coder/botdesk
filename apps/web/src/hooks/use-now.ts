import { useSyncExternalStore } from "react";

/*
 * One shared clock for every "5m ago" label on the page.
 *
 * On the server (and during the first browser render) there is no clock: the hook
 * returns null and labels render empty. Right after hydration the real time appears.
 * This keeps the server HTML and the browser HTML identical, and it's why Next.js
 * never sees the current time during prerendering.
 */

const TICK_MS = 30_000;
const listeners = new Set<() => void>();
let current: number | null = null;
let timer: ReturnType<typeof setInterval> | undefined;

function subscribe(onTick: () => void) {
  listeners.add(onTick);
  if (!timer) {
    timer = setInterval(() => {
      current = Date.now();
      listeners.forEach((listener) => listener());
    }, TICK_MS);
  }
  return () => {
    listeners.delete(onTick);
    if (listeners.size === 0) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

function getSnapshot() {
  current ??= Date.now();
  return current;
}

/** The current time in ms, refreshed every 30s. `null` on the server. */
export function useNow(): number | null {
  return useSyncExternalStore(subscribe, getSnapshot, () => null);
}
