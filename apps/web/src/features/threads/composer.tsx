import { useMemo, useRef, useState } from "react";
import { ArrowUp, Paperclip, Square } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { actions, useBots, useCurrentUser, useIsReplying, useUsers } from "@/data/store";
import type { Thread } from "@/data/types";
import { activeMention, insertMention, rankMentionables, type ActiveMention } from "@/lib/mentions";
import { MENTION_LIST_ID, MentionSuggestions, mentionOptionId, type MentionOption } from "./mention-suggestions";

/**
 * Where you type. Enter sends, Shift+Enter adds a new line, and the box grows with
 * your text up to a limit. Typing @ opens a list of the bots and people in this chat;
 * pick one to insert its @handle. While a bot is replying, Send becomes Stop (until you
 * start typing again).
 */
export function Composer({ thread }: { thread: Thread }) {
  const [text, setText] = useState("");
  const [mention, setMention] = useState<ActiveMention | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const boxRef = useRef<HTMLTextAreaElement>(null);
  const canSend = text.trim().length > 0;
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
    if (!canSend) return;
    actions.sendMessage(thread.id, text.trim());
    setText("");
    setMention(null);
  }

  return (
    <form
      className="mx-auto w-full max-w-3xl px-3 pb-3 md:px-6 md:pb-5"
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
    >
      <div className="relative flex items-end gap-1 rounded-[22px] border bg-background p-1.5 shadow-xs focus-within:ring-2 focus-within:ring-ring/40">
        {listOpen && (
          <MentionSuggestions options={matches} activeIndex={matches.indexOf(highlighted!)} onPick={pick} onHover={setActiveIndex} />
        )}
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
          ref={boxRef}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            updateMention(e.target.value, e.target.selectionStart);
          }}
          // Moving the caret with arrows or a click can enter or leave an @word.
          onSelect={(e) => updateMention(e.currentTarget.value, e.currentTarget.selectionStart)}
          onBlur={() => setMention(null)}
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

/** The bots and people in this chat (not you), bots first, as the @ list shows them. */
function useMentionOptions(thread: Thread): MentionOption[] {
  const bots = useBots();
  const users = useUsers();
  const me = useCurrentUser();
  return useMemo(() => {
    const inChat = (type: "bot" | "user", id: string) => thread.participants.some((p) => p.type === type && p.id === id);
    const botOptions: MentionOption[] = bots
      .filter((b) => inChat("bot", b.id))
      .map((b) => ({ type: "bot", id: b.id, handle: b.handle, name: b.name, role: b.role, color: b.avatarColor, status: b.status }));
    const userOptions: MentionOption[] = users
      .filter((u) => u.id !== me?.id && inChat("user", u.id))
      .map((u) => ({ type: "user", id: u.id, handle: u.handle, name: u.name }));
    return [...botOptions, ...userOptions];
  }, [bots, users, me?.id, thread.participants]);
}

async function stop(threadId: string) {
  const result = await actions.stopReplies(threadId);
  if (!result.ok) toast.error(result.error);
}
