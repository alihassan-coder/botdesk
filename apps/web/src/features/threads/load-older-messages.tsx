import { useEffect, useEffectEvent, useRef, useTransition, type RefObject } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { actions } from "@/data/store";

/**
 * At the top of a long chat: brings in the page of messages before the oldest one shown. It starts
 * by itself as you scroll up to within a screen of the top, and the button does the same.
 * Only one page loads at a time. It sits above the scroller's content, not among the messages: the
 * scroller keeps what you were reading in place when messages come in before its first one.
 */
export function LoadOlderMessages({ threadId, oldestId, scrollRoot }: {
  threadId: string;
  /** The oldest message shown: once a page lands, the top is checked again. */
  oldestId: string;
  /** The scrolling element the top must come near. */
  scrollRoot: RefObject<HTMLElement | null>;
}) {
  const [loading, startLoading] = useTransition();
  const busy = useRef(false);
  const sentinel = useRef<HTMLDivElement>(null);

  function loadOlder() {
    if (busy.current) return;
    busy.current = true;
    startLoading(async () => {
      const result = await actions.loadOlderMessages(threadId);
      busy.current = false;
      if (!result.ok) toast.error(result.error);
    });
  }

  const onNearTop = useEffectEvent(loadOlder);

  // A fresh observer per page: it reports straight away, so if the top is still near once a page
  // has landed (a short page, a tall window), the next one loads too. A failed load waits for the
  // next scroll up or the button, so it never retries in a loop.
  useEffect(() => {
    const target = sentinel.current;
    if (!target || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) onNearTop();
      },
      { root: scrollRoot.current, rootMargin: "100% 0px 0px 0px" },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [scrollRoot, oldestId]);

  return (
    <div className="relative flex justify-center px-4 pt-4">
      <div ref={sentinel} aria-hidden className="absolute inset-x-0 top-0 h-px" />
      <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={loadOlder} disabled={loading}>
        {loading ? <><Spinner aria-hidden /> Loading earlier messages…</> : "Show earlier messages"}
      </Button>
    </div>
  );
}
