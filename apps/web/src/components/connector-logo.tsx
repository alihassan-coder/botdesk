import type { CSSProperties } from "react";
import { MessageSquare, Puzzle, Server, type LucideIcon } from "lucide-react";
import { siGithub, siGmail, siGooglecalendar, siHubspot, siLinear, siNotion, siStripe, type SimpleIcon } from "simple-icons";
import { cn } from "@/lib/utils";

/*
 * Brand marks come from simple-icons (CC0), imported one by one so the bundle keeps only these.
 * Slack isn't in simple-icons (removed at the brand's request), so it keeps a neutral icon:
 * never draw a lookalike. Add new connector ids here, not in screens.
 */
const LOGOS: Record<string, SimpleIcon> = {
  gmail: siGmail,
  gcal: siGooglecalendar,
  github: siGithub,
  linear: siLinear,
  notion: siNotion,
  hubspot: siHubspot,
  stripe: siStripe,
};

/** Neutral icons for connectors with no brand mark; anything else gets its initial. */
const FALLBACK: Record<string, LucideIcon> = {
  demo: Puzzle,
  mcp: Server,
  slack: MessageSquare,
};

/** True when a brand colour would vanish on a dark background (GitHub, Notion…). */
export function isNearBlack(hex: string): boolean {
  const rgb = hex.replace("#", "").match(/.{2}/g)?.map((h) => parseInt(h, 16) / 255);
  if (!rgb || rgb.length !== 3 || rgb.some(Number.isNaN)) return false;
  const linear = rgb.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2] < 0.03;
}

const TILE = {
  xs: "", // inline next to text: the glyph alone
  sm: "size-8 rounded-lg border bg-muted/50",
  md: "size-10 rounded-xl border bg-muted/50",
} as const;
const GLYPH = { xs: "size-3.5", sm: "size-4", md: "size-5" } as const;

export type ConnectorLogoSize = keyof typeof TILE;

/**
 * A connector's or plugin's logo: its brand mark in the brand colour, or a neutral fallback.
 * Pass `decorative` when the name is written next to it, so screen readers don't read it twice.
 */
export function ConnectorLogo({
  connectorId,
  name,
  size = "md",
  decorative = false,
  className,
}: {
  connectorId: string;
  name: string;
  size?: ConnectorLogoSize;
  decorative?: boolean;
  className?: string;
}) {
  const a11y = decorative ? { "aria-hidden": true } : { role: "img", "aria-label": name };
  const icon = LOGOS[connectorId];
  const Fallback = FALLBACK[connectorId];

  return (
    <span
      {...a11y}
      data-logo={icon ? "brand" : "fallback"}
      className={cn("inline-grid shrink-0 place-items-center", TILE[size], className)}
    >
      {icon ? (
        <svg
          viewBox="0 0 24 24"
          fill="currentColor"
          aria-hidden
          style={{ "--logo-color": `#${icon.hex}` } as CSSProperties}
          className={cn(GLYPH[size], "text-(color:--logo-color)", isNearBlack(icon.hex) && "dark:text-foreground")}
        >
          <path d={icon.path} />
        </svg>
      ) : Fallback ? (
        <Fallback aria-hidden className={cn(GLYPH[size], "text-muted-foreground")} />
      ) : (
        <span aria-hidden className={cn("font-semibold text-muted-foreground uppercase", size === "md" ? "text-sm" : "text-xs")}>
          {name.trim().charAt(0) || "?"}
        </span>
      )}
    </span>
  );
}
