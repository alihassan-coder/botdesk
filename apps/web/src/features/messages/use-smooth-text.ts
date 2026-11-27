import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "@/lib/scroll";

/**
 * How many more characters to show this frame: an eighth of what's waiting (at least one), so a
 * burst of words eases in over about a quarter of a second and a long backlog catches up fast.
 */
export function revealStep(waiting: number): number {
  return waiting <= 0 ? 0 : Math.max(1, Math.ceil(waiting / 8));
}

/**
 * A streaming reply's text, revealed smoothly instead of in the bursts it arrives in. Once the
 * reply is complete (or with reduced motion) the whole text shows at once. Never shows text that
 * isn't there: when the text is replaced (say, the saved reply), it starts from what fits.
 */
export function useSmoothText(text: string, streaming: boolean): string {
  const [shown, setShown] = useState(text.length);
  const target = useRef(text.length);
  const animate = streaming && !prefersReducedMotion();

  useEffect(() => {
    target.current = text.length;
  }, [text.length]);

  useEffect(() => {
    if (!animate) return;
    let frame = 0;
    const tick = () => {
      setShown((current) => {
        const at = Math.min(current, target.current);
        return at + revealStep(target.current - at);
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [animate]);

  if (!animate) return text;
  return text.slice(0, Math.min(shown, text.length));
}
