import { CheckIcon, CopyIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { ClockTime } from "@/components/time-ago";
import { Button } from "@/components/ui/button";
import type { Message } from "@/data/types";
import { cn } from "@/lib/utils";

/** The words of a message, as written (markdown included), for copying. */
export function messageText(message: Message): string {
  return message.parts
    .flatMap((part) => (part.type === "text" && part.text.trim() ? [part.text.trim()] : []))
    .join("\n\n");
}

/**
 * Under a finished message: Copy, and the time it was sent (group chats already show the time
 * by the author's name). Shown on hover or keyboard focus, always on touch screens.
 */
export function MessageActions({ message, isOwn, showTime }: { message: Message; isOwn: boolean; showTime: boolean }) {
  const text = messageText(message);
  if (!text || message.status === "streaming") return null;

  return (
    <div
      className={cn(
        "-mt-1 flex items-center gap-1.5 text-xs text-muted-foreground opacity-0 group-focus-within/message:opacity-100 group-hover/message:opacity-100 pointer-coarse:opacity-100 motion-safe:transition-opacity",
        isOwn && "flex-row-reverse",
      )}
    >
      <CopyMessageButton text={text} />
      {showTime && <ClockTime iso={message.createdAt} />}
    </div>
  );
}

function CopyMessageButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timeout = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timeout);
  }, [copied]);

  return (
    <>
      <Button
        variant="ghost"
        size="icon-xs"
        aria-label={copied ? "Copied" : "Copy message"}
        className="text-muted-foreground hover:text-foreground"
        onClick={() => {
          navigator.clipboard
            .writeText(text)
            .then(() => setCopied(true))
            .catch(() => {});
        }}
      >
        {copied ? <CheckIcon /> : <CopyIcon />}
      </Button>
      <span aria-live="polite" className="sr-only">
        {copied ? "Copied" : ""}
      </span>
    </>
  );
}
