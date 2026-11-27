import { useCallback, useEffect, useRef, useState } from "react";
import { actions } from "@/data/store";
import type { ComputerInput, ComputerKey } from "@/data/types";
import { textPieces } from "@/lib/browser";
import { computerKeyOf } from "@/lib/computer";

/** Typing is gathered this long, then sent as one piece of text. */
const TYPE_PAUSE_MS = 150;
/** Typed text goes in pieces of at most this many characters. */
const TYPED_PIECE = 200;
/** Wheel turns are sent at most this often, one scroll each. */
const SCROLL_EVERY_MS = 150;
/** A second click this soon, this close (in pixels on the page here), makes a double click instead of two. */
export const DOUBLE_CLICK_MS = 400;
const DOUBLE_CLICK_PX = 4;

type Point = { x: number; y: number };
/** A click waiting to see whether a second one makes it a double click. */
type HeldClick = { at: Point; client: Point; time: number; timer: ReturnType<typeof setTimeout> };

/**
 * Taking over a bot's cloud computer: what a person does to the live picture goes to the computer, in
 * the order it was done, one request at a time. Points are already in the picture's own pixels.
 * A click is held for a moment: a second one close by makes it a double click; anything else done
 * meanwhile (typing, a key, a scroll, a click elsewhere) sends it first. Typing waits a moment and goes
 * as one `type`. `onSent` runs after each (to refresh the picture). `stop()` (Take over off) drops a
 * held click. The API's refusal (`error`) shows until something works.
 */
export function useComputerTakeOver(botId: string, onSent: () => void) {
  const [error, setError] = useState("");
  const queue = useRef(Promise.resolve());
  const typed = useRef("");
  const typingTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const held = useRef<HeldClick | null>(null);
  const scroll = useRef<{ dy: number; at: Point } | null>(null);
  const scrollTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const send = useCallback((input: ComputerInput) => {
    queue.current = queue.current.then(async () => {
      const result = await actions.sendComputerInput(botId, input);
      setError(result.ok ? "" : result.error);
      onSent();
    });
  }, [botId, onSent]);

  /** A held click goes now, before whatever came after it. */
  const flushClick = useCallback(() => {
    const click = held.current;
    if (!click) return;
    clearTimeout(click.timer);
    held.current = null;
    send({ kind: "click", ...click.at });
  }, [send]);

  const flushTyping = useCallback(() => {
    clearTimeout(typingTimer.current);
    const text = typed.current;
    typed.current = "";
    for (const piece of textPieces(text, TYPED_PIECE)) send({ kind: "type", text: piece });
  }, [send]);

  /** Wheel turns gathered so far go now, before a click that came after them. */
  const flushScroll = useCallback(() => {
    clearTimeout(scrollTimer.current);
    scrollTimer.current = undefined;
    const turned = scroll.current;
    scroll.current = null;
    if (turned && turned.dy !== 0) send({ kind: "scroll", direction: turned.dy < 0 ? "up" : "down", ...turned.at });
  }, [send]);

  // At most one of typing and scrolling waits at a time, so each sends the other first: the order holds.
  const type = useCallback((text: string) => {
    flushClick();
    flushScroll();
    typed.current += text;
    clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(flushTyping, TYPE_PAUSE_MS);
  }, [flushClick, flushScroll, flushTyping]);

  const press = useCallback((key: ComputerKey) => {
    flushClick();
    flushScroll();
    flushTyping();
    send({ kind: "key", key });
  }, [flushClick, flushScroll, flushTyping, send]);

  const stop = useCallback(() => {
    if (held.current) clearTimeout(held.current.timer);
    held.current = null;
    clearTimeout(scrollTimer.current);
    scrollTimer.current = undefined;
    scroll.current = null;
    flushTyping();
  }, [flushTyping]);

  // Leaving still sends what was typed; a held click or scroll is dropped.
  useEffect(() => stop, [stop]);

  return {
    error,
    /** True when the key went to the computer (so this browser shouldn't act on it too). */
    key(e: { key: string; shiftKey: boolean; ctrlKey: boolean; metaKey: boolean; altKey: boolean }): boolean {
      const meaning = computerKeyOf(e);
      if (!meaning) return false;
      if (meaning.kind === "text") type(meaning.text);
      else press(meaning.key);
      return true;
    },
    /** A key from the buttons under the picture. */
    press,
    /** Pasted or typed in the text field: typed on the computer. */
    type,
    stop,
    /** `client` is where it was clicked on the page here (to tell a double click from two clicks apart). */
    click(at: Point, client: Point, time = performance.now()) {
      flushTyping();
      flushScroll();
      const first = held.current;
      if (first && time - first.time <= DOUBLE_CLICK_MS && near(first.client, client)) {
        clearTimeout(first.timer);
        held.current = null; // a third click starts afresh
        return send({ kind: "double_click", ...first.at });
      }
      flushClick();
      const timer = setTimeout(flushClick, DOUBLE_CLICK_MS);
      held.current = { at, client, time, timer };
    },
    rightClick(at: Point) {
      flushClick();
      flushTyping();
      flushScroll();
      send({ kind: "right_click", ...at });
    },
    wheel(deltaY: number, at: Point) {
      flushClick();
      flushTyping();
      scroll.current = { dy: (scroll.current?.dy ?? 0) + deltaY, at };
      if (!scrollTimer.current) scrollTimer.current = setTimeout(flushScroll, SCROLL_EVERY_MS);
    },
  };
}

const near = (a: Point, b: Point) => Math.abs(a.x - b.x) <= DOUBLE_CLICK_PX && Math.abs(a.y - b.y) <= DOUBLE_CLICK_PX;
