import type { HandoffPart, Message, TaskStatus } from "@/data/types";

/**
 * How far a handed-off Task has got (ADR 0014). A card never moves backwards: a replayed or
 * late event can carry an older state, and it's ignored.
 */
const RANK: Record<TaskStatus, number> = { queued: 0, working: 1, done: 2, failed: 2, cancelled: 2 };

export const taskRank = (status: TaskStatus) => RANK[status];
export const isTaskOpen = (status: TaskStatus) => RANK[status] < 2;

/** What a `task_updated` event says about a Task: the fields its card shows. */
export type TaskChange = Pick<HandoffPart, "taskId" | "status" | "resultMessageId" | "resultPreview" | "error" | "errorCode">;

/** The card with the change applied, or the same card when the change is older than it. */
export function withTaskChange(part: HandoffPart, change: TaskChange): HandoffPart {
  if (part.taskId !== change.taskId || RANK[change.status] < RANK[part.status]) return part;
  const { type, fromBotId, toBotId, task } = part;
  return { type, fromBotId, toBotId, task, ...change };
}

/** Every handoff card for this Task, in any message, gets the change. Untouched messages stay the same objects. */
export function withTaskChangeIn(messages: Message[], change: TaskChange): Message[] {
  return messages.map((m) => {
    if (!m.parts.some((p) => p.type === "handoff" && p.taskId === change.taskId)) return m;
    return { ...m, parts: m.parts.map((p) => (p.type === "handoff" ? withTaskChange(p, change) : p)) };
  });
}

/** The newer of two changes for the same Task (the second wins a tie, as it arrived later). */
export function newerTaskChange(known: TaskChange | undefined, change: TaskChange): TaskChange {
  return known && RANK[change.status] < RANK[known.status] ? known : change;
}

/** A preview is the reply's first characters, so its Markdown is cut mid-way: show it without bold and code marks. */
export const plainPreview = (preview: string) => preview.replace(/\*\*|__|`/g, "");

/** A result preview as the API makes it: whitespace collapsed, at most 280 characters. */
export function taskPreview(text: string): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > 280 ? `${flat.slice(0, 279)}…` : flat;
}
