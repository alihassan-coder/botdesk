import { useEffect } from "react";
import { isHexColor, readableTextOn } from "@/lib/color";
import { useStoredState } from "@/hooks/use-stored-state";

/** Brand accents a member can pick (Settings → Appearance). Ultramarine is BotDesk's own. */
export const ACCENTS = [
  { id: "ultramarine", label: "Ultramarine", light: "#3b30ff", dark: "#7b73ff" },
  { id: "teal", label: "Teal", light: "#0f8f7a", dark: "#2fc4a8" },
  { id: "rose", label: "Rose", light: "#e0245e", dark: "#ff6b95" },
  { id: "amber", label: "Amber", light: "#b86e00", dark: "#f5a524" },
  { id: "graphite", label: "Graphite", light: "#3a3a3c", dark: "#d1d1d6" },
] as const;

/** A preset's id, or any custom colour as "#rrggbb". */
export type Accent = (typeof ACCENTS)[number]["id"] | `#${string}`;

/** The chosen accent, remembered in this browser. */
export function useAccent() {
  return useStoredState<Accent>("botdesk.accent", "ultramarine");
}

/**
 * Repaints the app: overrides --brand (and the text colour on it) on <html>.
 * A custom colour gets a lighter version for dark mode, and black or white text, whichever reads better.
 */
export function applyAccent(accent: Accent) {
  const preset = ACCENTS.find((a) => a.id === accent);
  const custom = !preset && isHexColor(accent) ? accent : null;
  const light = preset?.light ?? custom ?? ACCENTS[0].light;
  const dark = preset?.dark ?? (custom ? `color-mix(in oklch, ${custom} 70%, white)` : ACCENTS[0].dark);
  const text = custom ? readableTextOn(custom) : "#ffffff";

  const style = document.getElementById("botdesk-accent") ?? Object.assign(document.createElement("style"), { id: "botdesk-accent" });
  style.textContent = `:root{--brand:${light};--brand-foreground:${text}} .dark{--brand:${dark};--brand-foreground:${custom ? "#000000" : "#ffffff"}}`;
  document.head.appendChild(style);
}

/** Applies the saved accent when the app loads. Mounted once in the app shell. */
export function useApplySavedAccent() {
  const [accent] = useAccent();
  useEffect(() => applyAccent(accent), [accent]);
}
