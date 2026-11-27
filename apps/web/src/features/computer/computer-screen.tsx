import { useEffect, useEffectEvent, useId, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Switch } from "@/components/ui/switch";
import type { Bot } from "@/data/types";
import { toPagePoint } from "@/lib/browser";
import { ComputerKeys } from "./computer-keys";
import { useComputerScreen } from "./use-computer-screen";
import { useComputerTakeOver } from "./use-computer-take-over";

/** Two presses of Escape this close together step out of the screen instead of reaching it. */
const STEP_OUT_MS = 600;

/**
 * A running cloud computer's screen, live, and Take over. Off (the default), the picture is only to
 * watch. On, it's a focusable frame: clicks (a double click, a right click), typing, keys and the wheel
 * go to the computer, mapped from the picture's shown size to its own pixels; buttons below press keys a
 * touch screen lacks, and a field types longer text. Esc twice leaves the frame, so the keyboard is never stuck.
 */
export function ComputerScreen({ bot }: { bot: Bot }) {
  const [takingOver, setTakingOver] = useState(false);
  const screen = useComputerScreen(bot.id, true);
  const takeOver = useComputerTakeOver(bot.id, screen.soon);
  const frame = useRef<HTMLDivElement>(null);
  const picture = useRef<HTMLImageElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const lastEscape = useRef(-Infinity);
  const switchId = useId();
  const hintId = useId();

  /** Where on the computer's screen a point of the shown picture is, in its own pixels. */
  const pointAt = (clientX: number, clientY: number) => {
    const img = picture.current;
    if (!img?.naturalWidth || !img.naturalHeight) return null;
    return toPagePoint(clientX, clientY, img.getBoundingClientRect(), { width: img.naturalWidth, height: img.naturalHeight });
  };

  // React's wheel listener can't stop the pane from scrolling, so this one is added by hand.
  const onWheel = useEffectEvent((e: WheelEvent) => {
    e.preventDefault();
    const at = pointAt(e.clientX, e.clientY);
    if (at) takeOver.wheel(e.deltaY, at);
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

  const shown = screen.src ? (
    // eslint-disable-next-line @next/next/no-img-element -- a fresh blob: picture every second; next/image can't show those
    <img ref={picture} src={screen.src} draggable={false} alt={`${bot.name}'s computer screen`} className="block h-auto w-full select-none" />
  ) : (
    <p className="grid aspect-[16/10] place-items-center text-sm text-muted-foreground">{screen.problem || "Connecting to the screen…"}</p>
  );

  return (
    <div className="flex flex-col gap-3">
      {takingOver ? (
        <div ref={frame} role="application" tabIndex={0} aria-label={`${bot.name}'s computer, taking over`} aria-describedby={hintId}
          onKeyDown={onKeyDown}
          onPaste={(e) => {
            const text = e.clipboardData.getData("text");
            if (!text) return;
            e.preventDefault();
            takeOver.type(text);
          }}
          onClick={(e) => {
            const at = pointAt(e.clientX, e.clientY);
            if (at) takeOver.click(at, e.detail);
          }}
          onContextMenu={(e) => {
            e.preventDefault();
            const at = pointAt(e.clientX, e.clientY);
            if (at) takeOver.rightClick(at);
          }}
          className="cursor-default overflow-hidden rounded-xl bg-muted ring-2 ring-brand/60 outline-none focus:ring-4 focus:ring-brand">
          {shown}
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-muted">{shown}</div>
      )}
      {screen.src && screen.problem && <p className="text-xs text-pretty text-muted-foreground">{screen.problem} Showing the last picture.</p>}

      <div className="flex items-center justify-between gap-3">
        <label htmlFor={switchId} className="text-sm font-medium">Take over</label>
        <Switch id={switchId} ref={toggle} checked={takingOver} onCheckedChange={switchTakeOver} />
      </div>
      <p id={hintId} className="-mt-1 text-xs text-pretty text-muted-foreground">
        {takingOver
          ? "Clicks, typing and scrolling go to the computer; right-click for its menu. Press Esc twice to step out."
          : `Watching only. Take over to use ${bot.name}'s computer yourself.`}
      </p>
      {takeOver.error && <p role="alert" className="text-xs text-pretty text-destructive">{takeOver.error}</p>}
      {takingOver && <ComputerKeys botName={bot.name} onKey={takeOver.press} onType={takeOver.type} />}
    </div>
  );
}
