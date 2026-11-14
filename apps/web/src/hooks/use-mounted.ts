import { useSyncExternalStore } from "react";

const noop = () => () => {};

/**
 * False on the server and during hydration, true afterwards. For values only the browser
 * knows (the theme next-themes reads from localStorage): render a neutral state until this
 * is true, so the server HTML and the first browser render match (no hydration error).
 */
export function useMounted(): boolean {
  return useSyncExternalStore(noop, () => true, () => false);
}
