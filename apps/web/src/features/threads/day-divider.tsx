import { useEffect, useMemo, useState, type RefObject } from "react";
import { useMessageScrollerVisibility } from "@/components/ui/message-scroller";
import type { Message } from "@/data/types";
import { useNow } from "@/hooks/use-now";
import { dayKey, dayLabel } from "@/lib/days";
import { cn } from "@/lib/utils";

const CHIP = "rounded-full px-3 py-1 text-xs font-medium tabular-nums";

/**
 * The day above the first message of each day: "Today", "Yesterday", "Tuesday", "November 19".
 * It sits inside that message's item (see MessageList), so the scroller's first item is always a
 * message. Reads the clock itself, so "Today" turns into "Yesterday" at midnight without the
 * whole list rendering again.
 */
export function DayDivider({ at }: { at: string }) {
  const now = useNow();
  return (
    <div className="flex justify-center pb-5">
      <time dateTime={dayKey(at)} className={cn(CHIP, "bg-muted text-muted-foreground")}>
        {now === null ? " " : dayLabel(at, now)}
      </time>
    </div>
  );
}

const SHOWN_AFTER_SCROLL_MS = 1200;
const SCROLL_KEYS = new Set(["ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End", " "]);

/**
 * While you scroll, the day you're looking at floats at the top of the chat, and fades a moment
 * after you stop. It repeats what the dividers say, so screen readers skip it.
 */
export function FloatingDay({ messages, viewport }: { messages: Message[]; viewport: RefObject<HTMLElement | null> }) {
  const { visibleMessageIds } = useMessageScrollerVisibility();
  const now = useNow();
  const [scrolling, setScrolling] = useState(false);
  const createdAt = useMemo(() => new Map(messages.map((m) => [m.id, m.createdAt])), [messages]);

  useEffect(() => {
    const el = viewport.current;
    if (!el) return;
    let hide: ReturnType<typeof setTimeout> | undefined;
    // Only a scroll that follows your own input counts (a wheel, a swipe, a scroll key, dragging the
    // scrollbar): the chat following a reply, or gliding down after you send, scrolls too.
    let yoursAt = -Infinity;
    const yours = () => void (yoursAt = performance.now());
    const onKey = (event: KeyboardEvent) => SCROLL_KEYS.has(event.key) && yours();
    const onScroll = () => {
      // Near the top the first divider is in view already.
      if (el.scrollTop < 24 || performance.now() - yoursAt > SHOWN_AFTER_SCROLL_MS) return;
      setScrolling(true);
      clearTimeout(hide);
      hide = setTimeout(() => setScrolling(false), SHOWN_AFTER_SCROLL_MS);
    };
    const inputs = ["wheel", "touchmove", "pointerdown"] as const;
    inputs.forEach((name) => el.addEventListener(name, yours, { passive: true }));
    el.addEventListener("keydown", onKey);
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      inputs.forEach((name) => el.removeEventListener(name, yours));
      el.removeEventListener("keydown", onKey);
      el.removeEventListener("scroll", onScroll);
      clearTimeout(hide);
    };
  }, [viewport]);

  const top = visibleMessageIds.map((id) => createdAt.get(id)).find(Boolean);
  if (!top || now === null) return null;
  return (
    <div
      aria-hidden="true"
      data-shown={scrolling}
      className="pointer-events-none absolute inset-x-0 top-3 z-10 flex justify-center opacity-0 transition-[opacity,translate] duration-200 ease-out -translate-y-1 data-[shown=true]:translate-y-0 data-[shown=true]:opacity-100 motion-reduce:transition-none"
    >
      <span className={cn(CHIP, "border bg-background/95 text-muted-foreground shadow-sm backdrop-blur-sm")}>{dayLabel(top, now)}</span>
    </div>
  );
}
