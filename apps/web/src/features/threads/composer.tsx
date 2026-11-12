import { useState } from "react";
import { ArrowUp, Paperclip, Square } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { actions, useIsReplying } from "@/data/store";
import type { Thread } from "@/data/types";

/**
 * Where you type. Enter sends, Shift+Enter adds a new line, and the box grows with
 * your text up to a limit. @mentions are recognised when the message is sent.
 * While a bot is replying, Send becomes Stop (until you start typing again).
 */
export function Composer({ thread }: { thread: Thread }) {
  const [text, setText] = useState("");
  const canSend = text.trim().length > 0;
  const isReplying = useIsReplying(thread.id);

  function send() {
    if (!canSend) return;
    actions.sendMessage(thread.id, text.trim());
    setText("");
  }

  return (
    <form
      className="mx-auto w-full max-w-3xl px-3 pb-3 md:px-6 md:pb-5"
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
    >
      <div className="flex items-end gap-1 rounded-[22px] border bg-background p-1.5 shadow-xs focus-within:ring-2 focus-within:ring-ring/40">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="shrink-0 rounded-full"
          aria-label="Attach a file"
          onClick={() => toast("Attachments come in a later slice.")}
        >
          <Paperclip />
        </Button>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              send();
            }
          }}
          rows={1}
          placeholder={`Message ${thread.title}`}
          aria-label={`Message ${thread.title}`}
          className="field-sizing-content max-h-44 min-h-9 flex-1 resize-none bg-transparent px-1 py-2 text-[15px] outline-none placeholder:text-muted-foreground"
        />
        {isReplying && !canSend ? (
          <Button type="button" size="icon" className="shrink-0 rounded-full" onClick={() => stop(thread.id)} aria-label="Stop replying">
            <Square className="fill-current" />
          </Button>
        ) : (
          <Button type="submit" size="icon" className="shrink-0 rounded-full" disabled={!canSend} aria-label="Send">
            <ArrowUp />
          </Button>
        )}
      </div>
    </form>
  );
}

async function stop(threadId: string) {
  const result = await actions.stopReplies(threadId);
  if (!result.ok) toast.error(result.error);
}
