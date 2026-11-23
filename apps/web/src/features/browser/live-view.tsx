import { useCallback, useEffect, useEffectEvent, useId, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Switch } from "@/components/ui/switch";
import { actions } from "@/data/store";
import type { Bot, BotBrowser } from "@/data/types";
import { OpenPageForm } from "./open-page-form";
import { useLiveScreen } from "./use-live-screen";
import { useTakeOver } from "./use-take-over";

/** Two presses of Escape this close together step out of the page instead of reaching it. */
const STEP_OUT_MS = 600;

/**
 * An open browser: its page, a live picture of it, and Take over. Off (the default), the picture is
 * only to watch. On, the picture is a focusable frame: clicks, typing, keys and the wheel go to the
 * page, and an address field opens another page. Esc twice leaves the frame, so the keyboard is never stuck.
 */
export function LiveView({ bot, browser }: { bot: Bot; browser: BotBrowser }) {
  const [takingOver, setTakingOver] = useState(false);
  const reload = useCallback(() => void actions.loadBrowser(bot.id), [bot.id]);
  const screen = useLiveScreen(browser.screenUrl, reload);
  const takeOver = useTakeOver(bot.id, browser, screen.soon);
  const frame = useRef<HTMLDivElement>(null);
  const picture = useRef<HTMLImageElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const lastEscape = useRef(-Infinity);
  const switchId = useId();
  const hintId = useId();

  // React's wheel listener can't stop the pane from scrolling, so this one is added by hand.
  const onWheel = useEffectEvent((e: WheelEvent) => {
    e.preventDefault();
    takeOver.wheel(e.deltaY, e.deltaMode);
  });
  useEffect(() => {
    const el = frame.current;
    if (!takingOver || !el) return;
    const listener = (e: WheelEvent) => onWheel(e);
    el.addEventListener("wheel", listener, { passive: false });
    return () => el.removeEventListener("wheel", listener);
  }, [takingOver]);

  const switchTakeOver = (on: boolean) => {
    flushSync(() => setTakingOver(on));
    if (on) frame.current?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      if (e.timeStamp - lastEscape.current < STEP_OUT_MS) {
        e.preventDefault();
        toggle.current?.focus();
        return;
      }
      lastEscape.current = e.timeStamp;
    }
    if (takeOver.key(e)) e.preventDefault();
  };

  const shown = screen.src && (
    // eslint-disable-next-line @next/next/no-img-element -- a fresh picture every second; next/image would cache and resize it
    <img ref={picture} src={screen.src} onLoad={screen.onLoad} onError={screen.onError} draggable={false}
      alt={`What ${bot.name}'s browser shows: ${browser.title || browser.url || "a page"}`} className="size-full object-contain select-none" />
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium" title={browser.title}>{browser.title || "Untitled page"}</p>
        {browser.url && <p className="truncate font-mono text-xs text-muted-foreground" title={browser.url}>{browser.url}</p>}
      </div>

      {takingOver ? (
        <div ref={frame} role="application" tabIndex={0} aria-label={`${bot.name}'s browser, taking over`} aria-describedby={hintId}
          style={{ aspectRatio: `${browser.width} / ${browser.height}` }} onKeyDown={onKeyDown}
          onPaste={(e) => {
            const text = e.clipboardData.getData("text");
            if (!text) return;
            e.preventDefault();
            takeOver.paste(text);
          }}
          onClick={(e) => picture.current && takeOver.click(e.clientX, e.clientY, picture.current.getBoundingClientRect())}
          className="cursor-default overflow-hidden rounded-xl bg-muted ring-2 ring-brand/60 outline-none focus:ring-4 focus:ring-brand">
          {shown}
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-muted" style={{ aspectRatio: `${browser.width} / ${browser.height}` }}>
          {shown}
        </div>
      )}

      <div className="flex items-center justify-between gap-3">
        <label htmlFor={switchId} className="text-sm font-medium">Take over</label>
        <Switch id={switchId} ref={toggle} checked={takingOver} onCheckedChange={switchTakeOver} />
      </div>
      <p id={hintId} className="-mt-1 text-xs text-pretty text-muted-foreground">
        {takingOver
          ? "Clicks, typing and scrolling go to the page. Press Esc twice to step out."
          : `Watching only. Take over to use the page yourself, for example to sign ${bot.name} in.`}
      </p>
      {takeOver.error && <p role="alert" className="text-xs text-pretty text-destructive">{takeOver.error}</p>}
      {takingOver && <OpenPageForm bot={bot} onOpened={screen.soon} />}
    </div>
  );
}
