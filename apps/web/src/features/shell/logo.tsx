import { cn } from "@/lib/utils";

/*
 * The botdesk mark (logo v7): the b and d share one infinity loop.
 * Geometry is copied from docs/design/logo/v7/svg/mark-black.svg; it paints with
 * currentColor so it follows the text colour in light and dark mode.
 */

export function BotdeskMark({ className, weight = 10.5 }: { className?: string; weight?: number }) {
  return (
    <svg viewBox="11.25 10.75 77.5 78" aria-hidden className={cn("size-6 shrink-0", className)}>
      <g fill="none" stroke="currentColor" strokeWidth={weight} strokeLinecap="round" strokeLinejoin="round">
        <path d="M16.5 16 V68 M83.5 16 V68" />
        <path d="M45.347 60.12 A15.5 15.5 0 1 0 45.347 75.88 L54.653 60.12 A15.5 15.5 0 1 1 54.653 75.88 Z" />
      </g>
    </svg>
  );
}

/** Mark + name, as in the sidebar header. Heavier mark weight to match the bold text (see logo README). */
export function BotdeskLockup({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <BotdeskMark weight={14} className="size-[22px]" />
      <span className="text-[17px] font-semibold tracking-[-0.04em]">botdesk</span>
    </span>
  );
}
