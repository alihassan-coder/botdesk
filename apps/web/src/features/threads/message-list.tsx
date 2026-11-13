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
import { LoadOlderMessages } from "./load-older-messages";
import { MessageItem } from "./message-item";
import { RunAttentionNotices } from "./run-attention-notice";

/** The scrolling conversation. Opens at the newest message and follows new ones as they arrive. */
export function MessageList({ thread }: { thread: Thread }) {
  const messages = useThreadMessages(thread.id);
  const load = useThreadLoad(thread.id);

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
        <MessageScrollerViewport aria-label={`Conversation with ${thread.title}`}>
          <MessageScrollerContent className="mx-auto w-full max-w-3xl gap-5 px-4 py-6 md:px-6">
            {load?.hasOlder && <LoadOlderMessages threadId={thread.id} />}
            {messages.map((message) => (
              <MessageScrollerItem key={message.id} messageId={message.id}>
                <MessageItem message={message} isGroup={thread.kind === "group"} />
              </MessageScrollerItem>
            ))}
            <RunAttentionNotices threadId={thread.id} />
          </MessageScrollerContent>
        </MessageScrollerViewport>
        <MessageScrollerButton />
      </MessageScroller>
    </MessageScrollerProvider>
  );
}
