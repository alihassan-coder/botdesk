import { useMemo, useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { actions, useIsReplying } from "@/data/store";
import type { Thread } from "@/data/types";
import { activeMention, insertMention, rankMentionables, type ActiveMention } from "@/lib/mentions";
import { cn } from "@/lib/utils";
import { AttachFilesButton } from "./attach-files-button";
import { AttachmentChips } from "./attachment-chips";
import { MENTION_LIST_ID, MentionSuggestions, mentionOptionId, type MentionOption } from "./mention-suggestions";
import { useAttachments } from "./use-attachments";
import { useFileDrop } from "@/hooks/use-file-drop";
import { useMentionOptions } from "./use-mention-options";

/**
 * Where you type. Enter sends, Shift+Enter adds a new line, and the box grows with
 * your text up to a limit. Typing @ opens a list of the bots and people in this chat;
 * pick one to insert its @handle. Files come in with the paperclip, by dropping them on the box
 * or by pasting; each uploads at once and goes with the message. While a bot is replying, Send
 * becomes Stop (until you start writing again).
 */
export function Composer({ thread }: { thread: Thread }) {
  const [text, setText] = useState("");
  const [mention, setMention] = useState<ActiveMention | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const boxRef = useRef<HTMLTextAreaElement>(null);
  const attachments = useAttachments(thread);
  const drop = useFileDrop((files) => attachments.add(files));
  const hasText = text.trim().length > 0;
  const canSend = !attachments.isUploading && (hasText || attachments.uploaded.length > 0);
  const isReplying = useIsReplying(thread.id);
  const options = useMentionOptions(thread);

  const matches = useMemo(() => (mention ? rankMentionables(mention.query, options) : []), [mention, options]);
  const listOpen = matches.length > 0;
  const highlighted = listOpen ? matches[Math.min(activeIndex, matches.length - 1)] : undefined;

  function updateMention(value: string, caret: number) {
    const next = activeMention(value, caret);
    setMention(next);
    if (next?.query !== mention?.query || next?.start !== mention?.start) setActiveIndex(0);
  }

  function pick(option: MentionOption) {
    const box = boxRef.current;
    if (!mention || !box) return;
    const next = insertMention(text, mention, box.selectionStart, option.handle);
    setText(next.text);
    setMention(null);
    // Put the caret right after the inserted handle once React has rendered the new text.
    requestAnimationFrame(() => {
      box.focus();
      box.setSelectionRange(next.caret, next.caret);
    });
  }

  function send() {
    if (attachments.isUploading) {
      attachments.announce("Wait for the files to finish uploading.");
      return;
    }
    if (!canSend) return;
    actions.sendMessage(thread.id, text.trim(), attachments.uploaded);
    setText("");
    setMention(null);
    attachments.clear();
  }

  // Remove and Retry go away under the pointer, so the keyboard carries on in the box.
  const backToBox = (act: (key: number) => void) => (key: number) => {
    act(key);
    boxRef.current?.focus();
  };

  return (
    <form
      className="mx-auto w-full max-w-3xl px-3 pb-3 md:px-6 md:pb-5"
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
      {...drop.handlers}
    >
      <div
        className={cn(
          "relative rounded-[22px] border bg-background p-1.5 shadow-xs focus-within:ring-2 focus-within:ring-ring/40",
          drop.dragging && "border-brand ring-2 ring-brand/30",
        )}
      >
        {listOpen && (
          <MentionSuggestions options={matches} activeIndex={matches.indexOf(highlighted!)} onPick={pick} onHover={setActiveIndex} />
        )}
        {attachments.drafts.length > 0 && (
          <AttachmentChips drafts={attachments.drafts} onRemove={backToBox(attachments.remove)} onRetry={backToBox(attachments.retry)} />
        )}
        <div className="flex items-end gap-1">
          <AttachFilesButton onFiles={(files) => attachments.add(files)} />
          <textarea
            ref={boxRef}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              updateMention(e.target.value, e.target.selectionStart);
            }}
            // Moving the caret with arrows or a click can enter or leave an @word.
            onSelect={(e) => updateMention(e.currentTarget.value, e.currentTarget.selectionStart)}
            onBlur={() => setMention(null)}
            onPaste={(e) => {
              // Pasted files attach. Excel and Word also put a picture of the selection beside its
              // text, so when there's text, the text is what was meant.
              const files = Array.from(e.clipboardData.files);
              if (files.length === 0 || e.clipboardData.types.includes("text/plain")) return;
              e.preventDefault();
              attachments.add(files, { pasted: true });
            }}
            onKeyDown={(e) => {
              if (listOpen && highlighted) {
                if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                  e.preventDefault();
                  const step = e.key === "ArrowDown" ? 1 : -1;
                  setActiveIndex((matches.indexOf(highlighted) + step + matches.length) % matches.length);
                  return;
                }
                if ((e.key === "Enter" && !e.shiftKey) || e.key === "Tab") {
                  e.preventDefault();
                  pick(highlighted);
                  return;
                }
                if (e.key === "Escape") {
                  e.preventDefault();
                  setMention(null);
                  return;
                }
              }
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                send();
              }
            }}
            rows={1}
            placeholder={`Message ${thread.title}`}
            aria-label={`Message ${thread.title}`}
            aria-autocomplete="list"
            aria-controls={listOpen ? MENTION_LIST_ID : undefined}
            aria-activedescendant={highlighted ? mentionOptionId(highlighted) : undefined}
            className="field-sizing-content max-h-44 min-h-9 flex-1 resize-none bg-transparent px-1 py-2 text-[15px] outline-none placeholder:text-muted-foreground"
          />
          {isReplying && !hasText && attachments.drafts.length === 0 ? (
            <Button type="button" size="icon" className="shrink-0 rounded-full" onClick={() => stop(thread.id)} aria-label="Stop replying">
              <Square className="fill-current" />
            </Button>
          ) : (
            <Button type="submit" size="icon" className="shrink-0 rounded-full" disabled={!canSend} aria-label="Send">
              <ArrowUp />
            </Button>
          )}
        </div>
        {drop.dragging && (
          <div aria-hidden className="pointer-events-none absolute inset-0 grid place-items-center rounded-[22px] bg-background/90 text-sm font-medium text-brand">
            Drop files to attach
          </div>
        )}
      </div>
      <p role="status" className="sr-only">{attachments.announcement}</p>
    </form>
  );
}

async function stop(threadId: string) {
  const result = await actions.stopReplies(threadId);
  if (!result.ok) toast.error(result.error);
}
