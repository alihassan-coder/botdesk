import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { ArrowUp, ChevronDown, ListEnd, Square, Zap } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Kbd } from "@/components/ui/kbd";
import { actions, useCurrentUser, useIsReplying, useThreadMessages } from "@/data/store";
import type { Delivery, Thread } from "@/data/types";
import { clearDraft, insertAtCaret, loadDraft, saveDraft, stepHistory } from "@/lib/drafts";
import { activeMention, insertMention, rankMentionables, type ActiveMention } from "@/lib/mentions";
import { cn } from "@/lib/utils";
import { RecordingBar } from "@/features/voice/recording-bar";
import { useVoiceInput } from "@/features/voice/use-voice-input";
import { VoiceButton } from "@/features/voice/voice-button";
import { useFileDrop } from "@/hooks/use-file-drop";
import { AttachFilesButton } from "./attach-files-button";
import { AttachmentChips } from "./attachment-chips";
import { MENTION_LIST_ID, MentionSuggestions, mentionOptionId, type MentionOption } from "./mention-suggestions";
import { useAttachments } from "./use-attachments";
import { useMentionOptions } from "./use-mention-options";

/**
 * Where you type. Enter sends, Shift+Enter adds a new line, and the box grows with your text.
 * Typing @ lists the bots and people in this chat. Files come in with the paperclip, by dropping
 * them on the box or by pasting. The microphone writes down what you say into the box (ADR 0021).
 *
 * What you write is kept in this browser until you send it, per chat; Up brings back what you sent
 * before. While a bot is working, Enter sends now (it reads the message at its next step) and
 * Alt+Enter queues the message for after it finishes (ADR 0022); Stop ends its work.
 */
export function Composer({ thread }: { thread: Thread }) {
  const [text, setText] = useState("");
  const [mention, setMention] = useState<ActiveMention | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [historyAt, setHistoryAt] = useState<number | null>(null);
  const boxRef = useRef<HTMLTextAreaElement>(null);
  const textRef = useRef(text);
  const caretRef = useRef<number | null>(null);
  const draftBeforeHistory = useRef("");
  const attachments = useAttachments(thread);
  const drop = useFileDrop((files) => attachments.add(files));
  const hasText = text.trim().length > 0;
  const canSend = !attachments.isUploading && (hasText || attachments.uploaded.length > 0);
  const isReplying = useIsReplying(thread.id);
  const options = useMentionOptions(thread);
  const sent = useSentTexts(thread.id);
  const worker = thread.kind === "dm" ? thread.title : "The bot";

  // The draft is read once hydrated, so the first render matches the server's (which has no storage).
  const hydrated = useSyncExternalStore(neverChanges, () => true, () => false);
  const [draftRead, setDraftRead] = useState(false);
  if (hydrated && !draftRead) {
    setDraftRead(true);
    const draft = loadDraft(thread.id);
    if (draft) setText(draft);
  }

  const browsingRef = useRef(false);
  useEffect(() => {
    textRef.current = text;
    browsingRef.current = historyAt !== null;
    if (historyAt !== null) return; // a message recalled from history isn't a draft
    const timer = setTimeout(() => saveDraft(thread.id, text), 250);
    return () => clearTimeout(timer);
  }, [text, thread.id, historyAt]);

  // Leaving the chat (or the page) right after typing still keeps the last keystrokes.
  useEffect(() => {
    const keep = () => {
      if (!browsingRef.current) saveDraft(thread.id, textRef.current);
    };
    window.addEventListener("pagehide", keep);
    return () => {
      window.removeEventListener("pagehide", keep);
      keep();
    };
  }, [thread.id]);

  // Asked each time a chat opens (cheap: the API keeps the answer), so a key added meanwhile turns voice on.
  useEffect(() => {
    void actions.loadVoice();
  }, [thread.id]);

  const voice = useVoiceInput({
    hint: useCallback(() => [thread.title, ...options.map((o) => o.name)].join(", "), [thread.title, options]),
    onText: useCallback((words: string) => {
      const next = insertAtCaret(textRef.current, caretRef.current ?? textRef.current.length, words);
      setText(next.text);
      setHistoryAt(null);
      // The box is back once the recording bar goes: place the caret after the words then.
      requestAnimationFrame(() => {
        const box = boxRef.current;
        box?.focus();
        box?.setSelectionRange(next.caret, next.caret);
      });
    }, []),
  });
  const talking = voice.phase !== "idle" || voice.transcribing;
  // However talking ends (words, nothing heard, an error, Cancel), the keyboard is back in the box.
  const wasTalking = useRef(false);
  useEffect(() => {
    if (wasTalking.current && !talking) requestAnimationFrame(() => boxRef.current?.focus());
    wasTalking.current = talking;
  }, [talking]);

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

  function send(delivery?: Delivery) {
    if (attachments.isUploading) {
      attachments.announce("Wait for the files to finish uploading.");
      return;
    }
    if (!canSend) return;
    actions.sendMessage(thread.id, text.trim(), attachments.uploaded, isReplying ? (delivery ?? "now") : undefined);
    if (isReplying && delivery === "queue") toast(`Queued. ${worker} answers it after it finishes.`);
    setText("");
    setMention(null);
    setHistoryAt(null);
    clearDraft(thread.id);
    attachments.clear();
  }

  /** Up and Down walk through what you sent in this chat, while the caret is on the first or last line. */
  function recall(direction: "up" | "down", box: HTMLTextAreaElement): boolean {
    const browsing = historyAt !== null;
    if (!browsing && (direction === "down" || text !== "")) return false;
    const caret = box.selectionStart;
    const onEdge = direction === "up" ? !text.slice(0, caret).includes("\n") : !text.slice(caret).includes("\n");
    if (!onEdge) return false;
    const next = stepHistory(sent, historyAt, direction);
    if (next === historyAt) return next !== null; // already at the oldest: stay, but keep the key
    if (!browsing) draftBeforeHistory.current = text;
    const value = next === null ? draftBeforeHistory.current : sent[next];
    setHistoryAt(next);
    setText(value);
    requestAnimationFrame(() => box.setSelectionRange(value.length, value.length));
    return true;
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
          "group/composer relative rounded-[22px] border bg-background shadow-xs motion-safe:transition-shadow focus-within:shadow-sm focus-within:ring-2 focus-within:ring-ring/40",
          drop.dragging && "border-brand ring-2 ring-brand/30",
          talking && "ring-2 ring-brand/30",
        )}
      >
        {listOpen && (
          <MentionSuggestions options={matches} activeIndex={matches.indexOf(highlighted!)} onPick={pick} onHover={setActiveIndex} />
        )}
        {attachments.drafts.length > 0 && (
          <div className="px-1.5 pt-1.5">
            <AttachmentChips drafts={attachments.drafts} onRemove={backToBox(attachments.remove)} onRetry={backToBox(attachments.retry)} />
          </div>
        )}
        {talking ? (
          <RecordingBar voice={voice} />
        ) : (
          <>
            <textarea
              ref={boxRef}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setHistoryAt(null); // editing a recalled message makes it yours
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
                if ((e.key === "ArrowUp" || e.key === "ArrowDown") && !e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey) {
                  if (recall(e.key === "ArrowUp" ? "up" : "down", e.currentTarget)) e.preventDefault();
                  return;
                }
                if (e.key === "Escape" && historyAt !== null) {
                  e.preventDefault();
                  setHistoryAt(null);
                  setText(draftBeforeHistory.current);
                  return;
                }
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send(e.altKey ? "queue" : "now");
                }
              }}
              rows={1}
              placeholder={`Message ${thread.title}`}
              aria-label={`Message ${thread.title}`}
              aria-autocomplete="list"
              aria-controls={listOpen ? MENTION_LIST_ID : undefined}
              aria-activedescendant={highlighted ? mentionOptionId(highlighted) : undefined}
              className="field-sizing-content block max-h-60 min-h-11 w-full resize-none bg-transparent px-4 pt-3 pb-1 text-[15px] leading-6 outline-none placeholder:text-muted-foreground"
            />
            <div className="flex items-center gap-0.5 px-1.5 pb-1.5">
              <AttachFilesButton
                onFiles={(files) => {
                  attachments.add(files);
                  boxRef.current?.focus();
                }}
              />
              <VoiceButton
                voice={voice}
                onStart={() => {
                  caretRef.current = boxRef.current?.selectionStart ?? null;
                }}
              />
              <KeyHint replying={isReplying} worker={worker} browsing={historyAt !== null} />
              <div className="ml-auto flex items-center gap-1.5">
                {isReplying && (
                  <Button type="button" variant="outline" size="icon" className="shrink-0 rounded-full" onClick={() => stop(thread.id)} aria-label="Stop replying">
                    <Square className="fill-current" />
                  </Button>
                )}
                {isReplying && canSend ? (
                  <SendWhileWorking worker={worker} onSend={send} />
                ) : (
                  !(isReplying && !canSend) && (
                    <Button type="submit" size="icon" className="shrink-0 rounded-full" disabled={!canSend} aria-label="Send">
                      <ArrowUp />
                    </Button>
                  )
                )}
              </div>
            </div>
          </>
        )}
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

const neverChanges = () => () => {};

/** What you sent in this chat, oldest first (for Up). */
function useSentTexts(threadId: string): string[] {
  const me = useCurrentUser().id;
  const messages = useThreadMessages(threadId);
  return useMemo(
    () =>
      messages
        .filter((m) => m.author.type === "user" && m.author.id === me && m.status !== "error")
        .map((m) => m.parts.flatMap((p) => (p.type === "text" ? [p.text] : [])).join("\n").trim())
        .filter(Boolean),
    [messages, me],
  );
}

/** The quiet line by the buttons saying what the keys do, shown while you're in the box. */
function KeyHint({ replying, worker, browsing }: { replying: boolean; worker: string; browsing: boolean }) {
  return (
    <p className="ml-2 hidden min-w-0 items-center gap-1 truncate text-xs text-muted-foreground opacity-0 group-focus-within/composer:opacity-100 motion-safe:transition-opacity md:flex">
      {browsing ? (
        <>
          <Kbd>↑</Kbd>
          <Kbd>↓</Kbd> earlier messages, <Kbd>Esc</Kbd> back to your draft
        </>
      ) : replying ? (
        <>
          {worker} is working. <Kbd>Enter</Kbd> sends now, <Kbd>Alt</Kbd>
          <Kbd>Enter</Kbd> queues
        </>
      ) : (
        <>
          <Kbd>Enter</Kbd> to send, <Kbd>Shift</Kbd>
          <Kbd>Enter</Kbd> for a new line
        </>
      )}
    </p>
  );
}

/** While a bot works: Send now (it reads the message at its next step), or Queue it for after (ADR 0022). */
function SendWhileWorking({ worker, onSend }: { worker: string; onSend: (delivery: Delivery) => void }) {
  return (
    <div className="flex items-center">
      <Button type="submit" size="sm" className="h-8 rounded-l-full rounded-r-none pr-2 pl-3">
        <Zap data-icon="inline-start" /> Send now
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" size="icon" className="h-8 w-7 rounded-l-none rounded-r-full border-l border-primary-foreground/20" aria-label="More ways to send">
            <ChevronDown />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" side="top" className="w-72">
          <DropdownMenuItem className="items-start gap-2.5 py-2" onSelect={() => onSend("now")}>
            <Zap className="mt-0.5" />
            <span className="flex-1">
              <span className="block font-medium">Send now</span>
              <span className="block text-xs text-muted-foreground">{worker} reads it at its next step and carries on.</span>
            </span>
            <Kbd>Enter</Kbd>
          </DropdownMenuItem>
          <DropdownMenuItem className="items-start gap-2.5 py-2" onSelect={() => onSend("queue")}>
            <ListEnd className="mt-0.5" />
            <span className="flex-1">
              <span className="block font-medium">Queue</span>
              <span className="block text-xs text-muted-foreground">{worker} answers it after it finishes.</span>
            </span>
            <Kbd>Alt+Enter</Kbd>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

async function stop(threadId: string) {
  const result = await actions.stopReplies(threadId);
  if (!result.ok) toast.error(result.error);
}
