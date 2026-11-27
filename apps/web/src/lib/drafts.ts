/**
 * What you were writing in each chat, kept in this browser (localStorage) so switching chats or
 * reloading never loses it. Only text: files are uploaded as soon as they're added. A blocked or
 * full storage just means no draft is kept; nothing breaks.
 */

const PREFIX = "botdesk.draft.";
const MAX_DRAFT = 20_000;

export function loadDraft(threadId: string): string {
  try {
    return localStorage.getItem(PREFIX + threadId) ?? "";
  } catch {
    return "";
  }
}

export function saveDraft(threadId: string, text: string): void {
  try {
    if (text.trim()) localStorage.setItem(PREFIX + threadId, text.slice(0, MAX_DRAFT));
    else localStorage.removeItem(PREFIX + threadId);
  } catch {
    // Private mode or full storage: the draft lives only in the box.
  }
}

export function clearDraft(threadId: string): void {
  saveDraft(threadId, "");
}

/**
 * Up and Down through what you sent in this chat, like a terminal's history. `sent` is oldest
 * first; `at` is where you are in it (null: your own draft). Returns the new place, or `at` when
 * there's nowhere further to go.
 */
export function stepHistory(sent: string[], at: number | null, direction: "up" | "down"): number | null {
  if (sent.length === 0) return null;
  if (direction === "up") return at === null ? sent.length - 1 : Math.max(0, at - 1);
  if (at === null) return null;
  return at + 1 < sent.length ? at + 1 : null;
}

/** Puts `insert` (dictated words) into `text` at the caret, with a space on either side where it needs one. */
export function insertAtCaret(text: string, caret: number, insert: string): { text: string; caret: number } {
  const before = text.slice(0, caret);
  const after = text.slice(caret);
  const lead = before && !/\s$/.test(before) ? " " : "";
  const tail = after && !/^\s/.test(after) ? " " : "";
  const next = `${before}${lead}${insert}${tail}${after}`;
  return { text: next, caret: before.length + lead.length + insert.length };
}
