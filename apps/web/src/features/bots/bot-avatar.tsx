import { cn } from "@/lib/utils";
import { initialOf } from "@/lib/format";
import type { BotAvatarColor, BotStatus } from "@/data/types";
import { BOT_STATUS } from "./bot-status";

/*
 * Temporary avatar until the bot avatar system is designed (docs/design, step 3):
 * a rounded square in the bot's colour with its first letter. No faces, no blobs.
 */

const COLOR_CLASS: Record<BotAvatarColor, string> = {
  indigo: "bg-indigo-600",
  violet: "bg-violet-600",
  sky: "bg-sky-600",
  emerald: "bg-emerald-600",
  amber: "bg-amber-500",
  rose: "bg-rose-600",
  orange: "bg-orange-500",
  slate: "bg-slate-600",
};

const SIZE_CLASS = {
  sm: "size-6 rounded-md text-[11px]",
  md: "size-9 rounded-[10px] text-sm",
  lg: "size-14 rounded-2xl text-xl",
};

interface BotAvatarProps {
  name: string;
  color: BotAvatarColor;
  size?: keyof typeof SIZE_CLASS;
  /** Shows a small status dot in the corner. */
  status?: BotStatus;
  className?: string;
}

export function BotAvatar({ name, color, size = "md", status, className }: BotAvatarProps) {
  return (
    <span className={cn("relative inline-flex shrink-0", className)}>
      <span
        aria-hidden
        className={cn("grid place-items-center font-semibold text-white select-none", COLOR_CLASS[color], SIZE_CLASS[size])}
      >
        {initialOf(name)}
      </span>
      {status && (
        <span
          title={BOT_STATUS[status].label}
          className={cn(
            "absolute -right-0.5 -bottom-0.5 size-3 rounded-full ring-2 ring-sidebar",
            BOT_STATUS[status].dotClass,
          )}
        />
      )}
    </span>
  );
}

/** Same shape for a human member: neutral colour, so bots stand out. */
export function MemberAvatar({ name, size = "md", className }: { name: string; size?: keyof typeof SIZE_CLASS; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid shrink-0 place-items-center rounded-full bg-muted font-semibold text-foreground select-none",
        SIZE_CLASS[size],
        "rounded-full",
        className,
      )}
    >
      {initialOf(name)}
    </span>
  );
}
