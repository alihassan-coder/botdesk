import { useEffect } from "react";
import { useStoredState } from "@/hooks/use-stored-state";

/** Brand accents a member can pick (Settings → Appearance). Ultramarine is BotDesk's own. */
export const ACCENTS = [
  { id: "ultramarine", label: "Ultramarine", light: "#3b30ff", dark: "#7b73ff" },
  { id: "teal", label: "Teal", light: "#0f8f7a", dark: "#2fc4a8" },
  { id: "rose", label: "Rose", light: "#e0245e", dark: "#ff6b95" },
  { id: "amber", label: "Amber", light: "#b86e00", dark: "#f5a524" },
  { id: "graphite", label: "Graphite", light: "#3a3a3c", dark: "#d1d1d6" },
] as const;

export type AccentId = (typeof ACCENTS)[number]["id"];

/** The chosen accent, remembered in this browser. */
export function useAccent() {
  return useStoredState<AccentId>("botdesk.accent", "ultramarine");
}

/** Repaints the app: overrides --brand on <html> with the accent's light and dark values. */
export function applyAccent(id: AccentId) {
  const choice = ACCENTS.find((a) => a.id === id) ?? ACCENTS[0];
  const style = document.getElementById("botdesk-accent") ?? Object.assign(document.createElement("style"), { id: "botdesk-accent" });
  style.textContent = `:root{--brand:${choice.light}} .dark{--brand:${choice.dark}}`;
  document.head.appendChild(style);
}

/** Applies the saved accent when the app loads. Mounted once in the app shell. */
export function useApplySavedAccent() {
  const [accent] = useAccent();
  useEffect(() => applyAccent(accent), [accent]);
}
