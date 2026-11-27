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
/** A second click this soon makes a double click instead of two. */
export const DOUBLE_CLICK_MS = 250;

type Point = { x: number; y: number };

/**
 * Taking over a bot's cloud computer: what a person does to the live picture goes to the computer, in
 * order, one request at a time. Points are already in the picture's own pixels. Typing waits a moment
 * and goes as one `type`; a key, a click or a scroll sends what was typed first. A click waits a moment
 * too, in case a second click makes it a double click. `onSent` runs after each (to refresh the picture).
 * The API's refusal (`error`) shows until something works.
 */
export function useComputerTakeOver(botId: string, onSent: () => void) {
  const [error, setError] = useState("");
  const queue = useRef(Promise.resolve());
  const typed = useRef("");
  const typingTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const clickTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const scroll = useRef<{ dy: number; at: Point } | null>(null);
  const scrollTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const send = useCallback((input: ComputerInput) => {
    queue.current = queue.current.then(async () => {
      const result = await actions.sendComputerInput(botId, input);
      setError(result.ok ? "" : result.error);
      onSent();
    });
  }, [botId, onSent]);

  const flushTyping = useCallback(() => {
    clearTimeout(typingTimer.current);
    const text = typed.current;
    typed.current = "";
    for (const piece of textPieces(text, TYPED_PIECE)) send({ kind: "type", text: piece });
  }, [send]);

  const type = useCallback((text: string) => {
    typed.current += text;
    clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(flushTyping, TYPE_PAUSE_MS);
  }, [flushTyping]);

  const press = useCallback((key: ComputerKey) => {
    flushTyping();
    send({ kind: "key", key });
  }, [flushTyping, send]);

  // Leaving (or turning Take over off) still sends what was typed; a click still waiting is dropped.
  useEffect(() => () => {
    clearTimeout(clickTimer.current);
    clearTimeout(scrollTimer.current);
    flushTyping();
  }, [flushTyping]);

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
    /** `count` is the event's click count (`detail`): 2 turns the waiting click into a double click. */
    click(at: Point, count: number) {
      flushTyping();
      clearTimeout(clickTimer.current);
      if (count >= 2) return send({ kind: "double_click", ...at });
      clickTimer.current = setTimeout(() => send({ kind: "click", ...at }), DOUBLE_CLICK_MS);
    },
    rightClick(at: Point) {
      flushTyping();
      clearTimeout(clickTimer.current);
      send({ kind: "right_click", ...at });
    },
    wheel(deltaY: number, at: Point) {
      scroll.current = { dy: (scroll.current?.dy ?? 0) + deltaY, at };
      if (scrollTimer.current) return;
      scrollTimer.current = setTimeout(() => {
        scrollTimer.current = undefined;
        const turned = scroll.current;
        scroll.current = null;
        if (!turned || turned.dy === 0) return;
        flushTyping();
        send({ kind: "scroll", direction: turned.dy < 0 ? "up" : "down", ...turned.at });
      }, SCROLL_EVERY_MS);
    },
  };
}
