import { useCallback, useEffect, useRef, useState } from "react";
import { actions } from "@/data/store";

/** How long between pictures of a cloud computer's screen while someone watches. */
export const SCREEN_EVERY_MS = 1000;
/** How soon after a click or typing the next picture is asked for. */
const AFTER_INPUT_MS = 300;
/** After a picture fails, the next try waits this long; after a few failures in a row, much longer. */
const RETRY_MS = 3000;
const SLOW_RETRY_MS = 30_000;
const QUICK_RETRIES = 3;
/** Answers that won't change by trying again: signed out, no access, no such bot or computer. */
const GIVE_UP = new Set([401, 403, 404]);

/**
 * A live picture of a bot's cloud computer (ADR 0020 §5), fetched as a JPEG and shown from a blob:
 * URL. One picture at a time: the next is asked for about a second after the last arrived (a slow
 * connection isn't flooded), only while `running`, only while this tab is visible, and never after
 * unmount. Each new picture's URL replaces (and frees) the one before. `soon()` asks for the next one
 * right after an input. A failure tries again in 3 s, then every 30 s after three in a row; signed
 * out, no access or no such computer (401, 403, 404) stops asking. A 409 (it stopped) asks for the
 * computer's state once.
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
    let failures = 0;
    let gaveUp = false;

    const schedule = (ms: number) => {
      clearTimeout(timer);
      timer = setTimeout(() => void grab(), ms);
    };

    async function grab() {
      // Hidden: nothing is asked for until the tab is back (see onVisibility).
      if (!alive || gaveUp || inFlight || document.visibilityState !== "visible") return;
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
        failures = 0;
        schedule(wantSoon ? AFTER_INPUT_MS : SCREEN_EVERY_MS);
        return;
      }
      failures += 1;
      if (GIVE_UP.has(result.status)) {
        gaveUp = true;
        return setProblem(`${result.error} Reopen the Computer tab to try again.`);
      }
      setProblem(result.error);
      // It stopped (409): ask for its state once, so the tab says so; the tab's own check does the rest.
      if (result.status === 409 && failures === 1) void actions.loadComputer(botId);
      schedule(failures < QUICK_RETRIES ? RETRY_MS : SLOW_RETRY_MS);
    }

    const onVisibility = () => {
      if (document.visibilityState === "visible" && !inFlight) schedule(0);
    };
    soonRef.current = () => {
      if (gaveUp) return;
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
