import { Info } from "lucide-react";
import type { Message } from "@/data/types";

/**
 * A note from BotDesk itself, not from anyone in the chat: for now, "Stopped a chain of bot
 * replies after 3 hops" when bots kept @mentioning each other past the hop limit (ADR 0009).
 * Centred and quiet, so it reads as a status line rather than a message.
 */
export function SystemNotice({ message }: { message: Message }) {
  const text = message.parts.flatMap((p) => (p.type === "text" ? [p.text] : [])).join(" ");
  return (
    <p role="status" className="mx-auto flex max-w-md items-center gap-2 rounded-full border bg-muted/50 px-3 py-1.5 text-center text-xs text-muted-foreground">
      <Info className="size-3.5 shrink-0" aria-hidden="true" />
      {text}
    </p>
  );
}
