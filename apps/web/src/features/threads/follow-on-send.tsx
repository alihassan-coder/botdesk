import { useEffect, useLayoutEffect, useRef, type RefObject } from "react";
import { useMessageScroller } from "@/components/ui/message-scroller";
import { useCurrentUser } from "@/data/store";
import type { Message } from "@/data/types";
import { glideToEnd, prefersReducedMotion } from "@/lib/scroll";

/**
 * When you send a message (or a file), the chat glides down to it, even if you had scrolled up;
 * with reduced motion it jumps. Once there, replies follow while you stay at the bottom (the
 * scroller's own following). Renders nothing; it sits inside the scroller to use it.
 *
 * The glide drives the viewport itself instead of the scroller's smooth scroll: while the scroller
 * follows, every change (your message landing, a reply starting) jumps straight to the end, which
 * would cut a smooth scroll short. It hands back to the scroller at the end.
 */
export function FollowOnSend({ viewport, messages }: { viewport: RefObject<HTMLElement | null>; messages: Message[] }) {
  const me = useCurrentUser().id;
  const { scrollToEnd } = useMessageScroller();
  const seen = useRef<{ count: number; lastId?: string } | null>(null);
  const stopGlide = useRef<(() => void) | null>(null);
  const last = messages.at(-1);
  const sent = last?.author.type === "user" && last.author.id === me;

  useLayoutEffect(() => {
    const before = seen.current;
    seen.current = { count: messages.length, lastId: last?.id };
    const el = viewport.current;
    // New and yours: not the chat opening, older messages coming in above, or your message being saved.
    if (!before || !sent || !el || messages.length <= before.count || last?.id === before.lastId) return;
    stopGlide.current?.();
    const landed = () => void scrollToEnd({ behavior: "instant" });
    if (prefersReducedMotion()) landed();
    else stopGlide.current = glideToEnd(el, landed);
  }, [messages.length, last?.id, sent, viewport, scrollToEnd]);

  useEffect(() => () => stopGlide.current?.(), []);

  return null;
}
