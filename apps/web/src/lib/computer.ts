import type { BotComputer, CloudComputer, ComputerKey } from "@/data/types";

/*
 * A bot's cloud computer (ADR 0020): its words in the UI, what a key press means on it, and what its
 * tools sent back. Pure, so it's tested without a browser.
 */

/** Orgo's page where people create the key BotDesk uses. */
export const ORGO_KEYS_URL = "https://www.orgo.ai/api-keys";

/** The bot details' Computer line. */
export function describeBotComputer(computer: BotComputer): string {
  return computer === "cloud" ? "Files and a cloud computer" : "Files and a browser";
}

/** Making, starting or stopping: the tab checks more often until it's done. */
export function isChanging(status: CloudComputer["status"]): boolean {
  return status === "creating" || status === "starting" || status === "stopping";
}

const STATUS_WORDS: Record<CloudComputer["status"], string> = {
  none: "No computer yet",
  creating: "Making its computer…",
  starting: "Starting…",
  running: "Running",
  stopping: "Stopping…",
  stopped: "Stopped",
  error: "Something went wrong",
};

export const computerStatusText = (status: CloudComputer["status"]) => STATUS_WORDS[status];

/** "2 vCPU · 8 GB · us-east": what's known of its size and place. */
export function computerSpecs(computer: CloudComputer): string {
  return [
    computer.cpu ? `${computer.cpu} vCPU` : "",
    computer.ram ? `${computer.ram} GB` : "",
    computer.region ?? "",
  ].filter(Boolean).join(" · ");
}

/** The browser's names for the keys the computer takes, in xdotool's words. */
const KEYS: Record<string, ComputerKey> = {
  Enter: "Enter", Tab: "Tab", Escape: "Escape", Backspace: "BackSpace", Delete: "Delete",
  ArrowUp: "Up", ArrowDown: "Down", ArrowLeft: "Left", ArrowRight: "Right",
  Home: "Home", End: "End", PageUp: "Page_Up", PageDown: "Page_Down",
};

/** Ctrl shortcuts that go to the computer. Ctrl+V stays here: the paste arrives as text and is typed. */
const CTRL_KEYS: Record<string, ComputerKey> = { c: "ctrl+c", a: "ctrl+a", l: "ctrl+l" };

export type ComputerKeyMeaning = { kind: "text"; text: string } | { kind: "key"; key: ComputerKey } | null;

/** What a key press means on the computer: text to type, a key, or nothing (it stays this browser's). */
export function computerKeyOf(e: { key: string; shiftKey: boolean; ctrlKey: boolean; metaKey: boolean; altKey: boolean }): ComputerKeyMeaning {
  if (e.metaKey) return null;
  // Only the exact shortcut: Ctrl+Shift+C (copy in a terminal, or this browser's tools) stays here.
  // Ctrl with Alt is AltGr on Windows keyboards, which types characters like @ and €.
  if (e.ctrlKey && !e.altKey) {
    const key = e.shiftKey ? undefined : CTRL_KEYS[e.key.toLowerCase()];
    return key ? { kind: "key", key } : null;
  }
  // A special key goes only on its own: the computer has no Shift+Tab, Shift+arrow or Alt+key.
  if (KEYS[e.key]) return e.shiftKey || e.altKey ? null : { kind: "key", key: KEYS[e.key] };
  if ([...e.key].length === 1) return { kind: "text", text: e.key };
  return null;
}

/** The buttons for keys a touch screen has no way to press (and shortcuts that would stay here). */
export const KEY_BUTTONS: { key: ComputerKey; label: string; name?: string }[] = [
  { key: "Enter", label: "Enter" },
  { key: "Tab", label: "Tab" },
  { key: "Escape", label: "Esc", name: "Escape" },
  { key: "BackSpace", label: "Backspace" },
  { key: "Up", label: "↑", name: "Up arrow" },
  { key: "Down", label: "↓", name: "Down arrow" },
  { key: "Left", label: "←", name: "Left arrow" },
  { key: "Right", label: "→", name: "Right arrow" },
  { key: "ctrl+c", label: "Ctrl+C" },
  { key: "ctrl+v", label: "Ctrl+V" },
  { key: "ctrl+a", label: "Ctrl+A" },
  { key: "ctrl+l", label: "Ctrl+L" },
];

/** The API's mark where it cut long output: "… 12345 bytes cut …". */
const CUT_MARK = /\n… \d+ bytes cut …\n/;

/** What `computer.run` and `computer.inspect` send back. */
export interface CommandResult {
  exitCode: number;
  output: string;
  seconds?: number;
  cwd?: string;
  /** The API kept only the first and last 8 KB (its mark is in `output`, or an older shape said `truncated`). */
  cut: boolean;
}

/** A command's result, if `result` looks like one (an older or failed call may have none). */
export function commandResult(result: unknown): CommandResult | undefined {
  if (!isRecord(result) || typeof result.exitCode !== "number") return undefined;
  return {
    exitCode: result.exitCode,
    output: typeof result.output === "string" ? result.output : "",
    ...(typeof result.seconds === "number" ? { seconds: result.seconds } : {}),
    ...(typeof result.cwd === "string" && result.cwd ? { cwd: result.cwd } : {}),
    cut: result.truncated === true || (typeof result.output === "string" && CUT_MARK.test(result.output)),
  };
}

/** What `computer.preview` sends back: a URL for a port. */
export function previewResult(result: unknown): { url: string; port?: number; access?: string } | undefined {
  if (!isRecord(result) || typeof result.url !== "string" || !/^https?:\/\//i.test(result.url)) return undefined;
  return {
    url: result.url,
    ...(typeof result.port === "number" ? { port: result.port } : {}),
    ...(typeof result.access === "string" ? { access: result.access } : {}),
  };
}

/** Only "link" opens for anyone with it; Orgo's other levels need someone in the Orgo workspace. */
export const isWorkspaceOnly = (access?: string) => access !== "link";

/** "0.4 s", "12 s", "2 min 5 s". */
export function formatSeconds(seconds: number): string {
  if (seconds < 10) return `${Math.round(seconds * 10) / 10} s`;
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)} min ${whole % 60} s`;
}

/** How many lines of output, for the toggle ("Output · 342 lines"). A trailing newline isn't a line. */
export function lineCount(output: string): number {
  if (!output) return 0;
  return output.replace(/\n$/, "").split("\n").length;
}

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;
