import { useCallback, useEffect, useRef, useState } from "react";
import { actions } from "@/data/store";
import type { BrowserInput } from "@/data/types";
import { keyMeaning, scrollDelta, textPieces, toPagePoint } from "@/lib/browser";

/** Typing is gathered this long, then sent as one piece of text. */
const TYPE_PAUSE_MS = 150;
/** Wheel turns are added up and sent at most this often. */
const SCROLL_EVERY_MS = 150;

interface Page { width: number; height: number }

/**
 * Taking over a bot's browser: what a person does to the live picture goes to the page, in order,
 * one request at a time. Typing waits a moment and goes as one `type`; a special key, a click or a
 * scroll sends what was typed first. `onSent` runs after each (to refresh the picture).
 * The API's refusal (`error`) shows until something works.
 */
export function useTakeOver(botId: string, page: Page, onSent: () => void) {
  const [error, setError] = useState("");
  const queue = useRef(Promise.resolve());
  const typed = useRef("");
  const typingTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const scrolled = useRef(0);
  const scrollTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const send = useCallback((input: BrowserInput) => {
    queue.current = queue.current.then(async () => {
      const result = await actions.sendBrowserInput(botId, input);
      setError(result.ok ? "" : result.error);
      onSent();
    });
  }, [botId, onSent]);

  const flushTyping = useCallback(() => {
    clearTimeout(typingTimer.current);
    const text = typed.current;
    typed.current = "";
    for (const piece of textPieces(text)) send({ kind: "type", text: piece });
  }, [send]);

  const type = useCallback((text: string) => {
    typed.current += text;
    clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(flushTyping, TYPE_PAUSE_MS);
  }, [flushTyping]);

  // Leaving (or turning Take over off) still sends what was typed.
  useEffect(() => () => flushTyping(), [flushTyping]);

  return {
    error,
    /** True when the key went to the page (so this browser shouldn't act on it too). */
    key(e: { key: string; shiftKey: boolean; ctrlKey: boolean; metaKey: boolean; altKey: boolean }): boolean {
      const meaning = keyMeaning(e);
      if (!meaning) return false;
      if (meaning.kind === "text") type(meaning.text);
      else {
        flushTyping();
        send(meaning);
      }
      return true;
    },
    paste: type,
    click(clientX: number, clientY: number, shown: DOMRect) {
      flushTyping();
      send({ kind: "click", ...toPagePoint(clientX, clientY, shown, page) });
    },
    wheel(deltaY: number, deltaMode: number) {
      scrolled.current += scrollDelta(deltaY, deltaMode);
      if (scrollTimer.current) return;
      scrollTimer.current = setTimeout(() => {
        scrollTimer.current = undefined;
        const dy = Math.max(-3000, Math.min(3000, scrolled.current));
        scrolled.current = 0;
        if (dy !== 0) {
          flushTyping();
          send({ kind: "scroll", dy });
        }
      }, SCROLL_EVERY_MS);
    },
  };
}
