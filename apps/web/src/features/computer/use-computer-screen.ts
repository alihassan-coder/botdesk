import { useCallback, useEffect, useRef, useState } from "react";
import { actions } from "@/data/store";

/** How long between pictures of a cloud computer's screen while someone watches. */
export const SCREEN_EVERY_MS = 1000;
/** How soon after a click or typing the next picture is asked for. */
const AFTER_INPUT_MS = 300;
/** After a picture fails, the next try waits this long. */
const RETRY_MS = 3000;

/**
 * A live picture of a bot's cloud computer (ADR 0020 §5), fetched as a JPEG and shown from a blob:
 * URL. One picture at a time: the next is asked for about a second after the last arrived (a slow
 * connection isn't flooded), only while `running`, only while this tab is visible, and never after
 * unmount. Each new picture's URL replaces (and frees) the one before. `soon()` asks for the next one
 * right after an input. A 409 (it stopped) reloads the computer's state in the store.
 */
export function useComputerScreen(botId: string, running: boolean) {
  const [src, setSrc] = useState("");
  const [problem, setProblem] = useState("");
  const soonRef = useRef(() => {});

  useEffect(() => {
    if (!running) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inFlight: AbortController | null = null;
    let wantSoon = false;
    let shown = "";

    const schedule = (ms: number) => {
      clearTimeout(timer);
      timer = setTimeout(() => void grab(), ms);
    };

    async function grab() {
      // Hidden: nothing is asked for until the tab is back (see onVisibility).
      if (!alive || inFlight || document.visibilityState !== "visible") return;
      wantSoon = false;
      const controller = new AbortController();
      inFlight = controller;
      const result = await actions.computerScreen(botId, controller.signal);
      inFlight = null;
      if (!alive) return;
      if (result.ok) {
        const url = URL.createObjectURL(result.picture);
        if (shown) URL.revokeObjectURL(shown);
        shown = url;
        setSrc(url);
        setProblem("");
        schedule(wantSoon ? AFTER_INPUT_MS : SCREEN_EVERY_MS);
      } else {
        setProblem(result.error);
        schedule(RETRY_MS);
      }
    }

    const onVisibility = () => {
      if (document.visibilityState === "visible" && !inFlight) schedule(0);
    };
    soonRef.current = () => {
      // A picture already on its way may show the screen from before; ask again as soon as it lands.
      if (inFlight) wantSoon = true;
      else schedule(AFTER_INPUT_MS);
    };

    schedule(0);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      alive = false;
      clearTimeout(timer);
      inFlight?.abort();
      document.removeEventListener("visibilitychange", onVisibility);
      soonRef.current = () => {};
      if (shown) URL.revokeObjectURL(shown);
      // The freed picture can't be shown again: start blank next time.
      setSrc("");
      setProblem("");
    };
  }, [botId, running]);

  const soon = useCallback(() => soonRef.current(), []);
  return { src, problem, soon };
}
