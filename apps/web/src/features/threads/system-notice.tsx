import { Info } from "lucide-react";
import type { Message } from "@/data/types";
import { RoutineCreatedPart } from "@/features/messages/small-parts";

/**
 * A note from BotDesk itself, not from anyone in the chat: "Stopped a chain of bot replies after 3
 * hops" (ADR 0009), "Routine: Morning digest" when a routine starts its run here, or the "Created a
 * routine" card linking to the routines page. Centred and quiet, so it reads as a status line.
 */
export function SystemNotice({ message }: { message: Message }) {
  const created = message.parts.find((p) => p.type === "routine-created");
  if (created) {
    return (
      <div role="status" className="mx-auto">
        <RoutineCreatedPart part={created} />
      </div>
    );
  }
  const text = message.parts.flatMap((p) => (p.type === "text" ? [p.text] : [])).join(" ");
  return (
    <p role="status" className="mx-auto flex max-w-md items-center gap-2 rounded-full border bg-muted/50 px-3 py-1.5 text-center text-xs text-muted-foreground">
      <Info className="size-3.5 shrink-0" aria-hidden="true" />
      {text}
    </p>
  );
}
