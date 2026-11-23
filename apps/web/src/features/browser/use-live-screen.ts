import { useCallback, useEffect, useRef, useState } from "react";

/** How long between pictures of a bot's screen while someone watches. */
export const SCREEN_EVERY_MS = 1000;
/** How soon after a click or typing the next picture is asked for. */
const AFTER_INPUT_MS = 150;

/** Every picture asked for gets its own number, so none is ever served from a cache. */
let frames = 0;

/**
 * A live picture of a bot's browser. `src` moves on about once a second, but only once the last
 * picture has arrived (a slow connection isn't flooded), only while this tab is visible, and never
 * after unmount. `soon()` asks for the next one right away, after a click or typing. A picture that
 * fails (the browser closed) calls `onMissing` and tries again a little later.
 */
export function useLiveScreen(screenUrl: string, onMissing: () => void) {
  const [frame, setFrame] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const loading = useRef(false);
  const wantSoon = useRef(false);

  const schedule = useCallback((ms: number) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      if (document.visibilityState !== "visible") return; // picks up again when the tab is back
      loading.current = true;
      wantSoon.current = false;
      setFrame(++frames);
    }, ms);
  }, []);

  useEffect(() => {
    if (!screenUrl) return;
    schedule(0);
    const onVisibility = () => {
      if (document.visibilityState === "visible" && !loading.current) schedule(0);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearTimeout(timer.current);
      loading.current = false;
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [screenUrl, schedule]);

  const onLoad = useCallback(() => {
    loading.current = false;
    schedule(wantSoon.current ? AFTER_INPUT_MS : SCREEN_EVERY_MS);
  }, [schedule]);

  const onError = useCallback(() => {
    loading.current = false;
    onMissing();
    schedule(SCREEN_EVERY_MS * 3);
  }, [onMissing, schedule]);

  const soon = useCallback(() => {
    // A picture already on its way may show the page from before; ask again as soon as it lands.
    if (loading.current) wantSoon.current = true;
    else schedule(AFTER_INPUT_MS);
  }, [schedule]);

  return { src: screenUrl && frame !== null ? `${screenUrl}?frame=${frame}` : "", onLoad, onError, soon };
}
