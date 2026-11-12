import { useId } from "react";
import { cn } from "@/lib/utils";
import { LOGO } from "./logo-data";

/*
 * The botdesk logo: the name in Outfit ExtraBold, with an online light on the o.
 * Shapes come from docs/design/logo (generated into logo-data.ts). Letters paint with
 * currentColor so they follow light and dark mode; the light uses the brand colour,
 * so it also follows a custom accent from Settings → Appearance.
 */

type Light = { cx: number; cy: number; r: number; halo: number };

/** The o with the light cut into it. `monochrome` paints the light like the letters. */
function OWithLight({ o, light, monochrome }: { o: string; light: Light; monochrome?: boolean }) {
  const maskId = useId();
  return (
    <>
      <mask id={maskId} maskUnits="userSpaceOnUse" x="-1000" y="-1000" width="3000" height="3000">
        <rect x="-1000" y="-1000" width="3000" height="3000" fill="#fff" />
        <circle cx={light.cx} cy={light.cy} r={light.halo} fill="#000" />
      </mask>
      <path d={o} fill="currentColor" mask={`url(#${maskId})`} />
      <circle cx={light.cx} cy={light.cy} r={light.r} fill={monochrome ? "currentColor" : "var(--brand)"} />
    </>
  );
}

/** The mark: the o with its online light. Used where the name doesn't fit (rail, loader). */
export function BotdeskMark({ className, monochrome }: { className?: string; monochrome?: boolean }) {
  const { viewBox, o, light } = LOGO.mark;
  return (
    <svg viewBox={viewBox.join(" ")} aria-hidden className={cn("size-6 shrink-0", className)}>
      <OWithLight o={o} light={light} monochrome={monochrome} />
    </svg>
  );
}

/** The full logo: the name itself. Height sets the size; width follows. */
export function BotdeskLockup({ className, monochrome }: { className?: string; monochrome?: boolean }) {
  const { viewBox, rest, o, light } = LOGO.wordmark;
  return (
    <svg
      viewBox={viewBox.join(" ")}
      role="img"
      aria-label="botdesk"
      className={cn("h-[22px] w-auto shrink-0", className)}
    >
      <path d={rest} fill="currentColor" />
      <OWithLight o={o} light={light} monochrome={monochrome} />
    </svg>
  );
}
