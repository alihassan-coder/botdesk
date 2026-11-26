import { useMemo, useRef } from "react";
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller";
import { Spinner } from "@/components/ui/spinner";
import { useThreadLoad, useThreadMessages } from "@/data/store";
import type { Thread } from "@/data/types";
import { startsADay } from "@/lib/days";
import { DayDivider, FloatingDay } from "./day-divider";
import { DmWelcome } from "./dm-welcome";
import { FollowOnSend } from "./follow-on-send";
import { LoadOlderMessages } from "./load-older-messages";
import { MessageItem } from "./message-item";
import { RunAttentionNotices } from "./run-attention-notice";
import { RunWaitingNotices } from "./run-waiting-notice";

/** The scrolling conversation. Opens at the newest message and follows new ones as they arrive. */
export function MessageList({ thread }: { thread: Thread }) {
  const messages = useThreadMessages(thread.id);
  const load = useThreadLoad(thread.id);
  const viewport = useRef<HTMLDivElement>(null);
  const newDay = useMemo(() => startsADay(messages), [messages]);

  if (messages.length === 0 && load?.status === "loading") {
    return (
      <div className="flex flex-1 items-center justify-center" aria-busy="true">
        <Spinner className="size-5 text-muted-foreground" />
        <span className="sr-only">Loading messages…</span>
      </div>
    );
  }

  if (messages.length === 0 && load?.status === "error") {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-center text-sm text-muted-foreground">
        These messages didn&apos;t load. Check your connection and reload the page.
      </div>
    );
  }

  if (messages.length === 0 && thread.kind === "dm" && thread.botId) return <DmWelcome botId={thread.botId} title={thread.title} />;

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-center text-sm text-muted-foreground">
        No messages yet. Say hi to {thread.title}.
      </div>
    );
  }

  return (
    <MessageScrollerProvider autoScroll defaultScrollPosition="end">
      <MessageScroller className="flex-1">
        <MessageScrollerViewport ref={viewport} aria-label={`Conversation with ${thread.title}`}>
          {/* Above the content, so the first item there is always a message: that's how the scroller
              tells older messages came in and keeps the one you were reading in place. */}
          {load?.hasOlder && load.status === "ready" && (
            <LoadOlderMessages threadId={thread.id} oldestId={messages[0].id} scrollRoot={viewport} />
          )}
          <MessageScrollerContent className="mx-auto w-full max-w-3xl gap-5 px-4 py-6 md:px-6">
            {messages.map((message, index) => (
              // The id and tabIndex let a handoff card's "View reply" scroll to a message and focus it.
              // A new day's divider goes inside its first message's item, never as an item of its own:
              // the scroller keeps your place when older messages load by watching which item is first.
              <MessageScrollerItem
                key={message.id}
                messageId={message.id}
                id={`message-${message.id}`}
                tabIndex={-1}
                className="rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              >
                {newDay[index] && <DayDivider at={message.createdAt} />}
                <MessageItem message={message} isGroup={thread.kind === "group"} dmBotId={thread.botId} />
              </MessageScrollerItem>
            ))}
            <RunWaitingNotices threadId={thread.id} />
            <RunAttentionNotices threadId={thread.id} />
          </MessageScrollerContent>
        </MessageScrollerViewport>
        <FloatingDay messages={messages} viewport={viewport} />
        <MessageScrollerButton />
      </MessageScroller>
      <FollowOnSend viewport={viewport} messages={messages} />
    </MessageScrollerProvider>
  );
}
