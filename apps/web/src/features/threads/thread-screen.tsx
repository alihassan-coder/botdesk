"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useIsMobile } from "@/hooks/use-mobile";
import { useStoredState } from "@/hooks/use-stored-state";
import { Spinner } from "@/components/ui/spinner";
import { actions, useBotsLoading, useThread } from "@/data/store";
import { Composer } from "./composer";
import { DetailsContent, DetailsPane } from "./details-pane";
import { MessageList } from "./message-list";
import { ThreadHeader } from "./thread-header";

const DESKTOP = "(min-width: 1280px)";

/**
 * A conversation: header, messages, composer, and the details pane.
 * Desktop shows details beside the chat; smaller screens open them in a sheet.
 */
export function ThreadScreen({ threadId }: { threadId: string }) {
  const thread = useThread(threadId);
  const chatsLoading = useBotsLoading();
  const isPhone = useIsMobile();
  const [paneOpen, setPaneOpen] = useStoredState("botdesk.detailsPane.open", true);
  const [paneWidth, setPaneWidth] = useStoredState("botdesk.detailsPane.width", 340);
  const [sheetOpen, setSheetOpen] = useState(false);

  // Opening a chat means you've seen it.
  useEffect(() => actions.markRead(threadId), [threadId]);

  // Load its messages and follow new ones while it's open (on the API; the mock has them already).
  // Waits for the chat list, so a reload straight into a chat works too.
  const found = thread !== undefined;
  useEffect(() => (found ? actions.openThread(threadId) : undefined), [threadId, found]);

  if (!thread && chatsLoading) return <ThreadLoading />;
  if (!thread) return <ThreadNotFound />;

  function toggleDetails() {
    if (window.matchMedia(DESKTOP).matches) setPaneOpen(!paneOpen);
    else setSheetOpen(true);
  }

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col">
        <ThreadHeader thread={thread} onToggleDetails={toggleDetails} />
        <MessageList thread={thread} />
        <Composer thread={thread} />
      </div>

      {paneOpen && <DetailsPane thread={thread} width={paneWidth} onResize={setPaneWidth} />}

      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        {/* The tab bar leaves room for the sheet's close button. */}
        <SheetContent
          side={isPhone ? "bottom" : "right"}
          className={`p-0 [&_[data-slot=tabs-list]]:mr-12 ${isPhone ? "h-[85svh] rounded-t-2xl" : "w-[360px]"}`}
        >
          <SheetTitle className="sr-only">Details for {thread.title}</SheetTitle>
          <DetailsContent thread={thread} />
        </SheetContent>
      </Sheet>
    </div>
  );
}

function ThreadLoading() {
  return (
    <div className="grid h-full place-items-center" aria-busy="true">
      <Spinner className="size-5 text-muted-foreground" />
      <span className="sr-only">Opening the chat…</span>
    </div>
  );
}

function ThreadNotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
      <h1 className="text-lg font-semibold">This chat doesn&apos;t exist</h1>
      <p className="text-sm text-muted-foreground">It may have been deleted, or the link is wrong.</p>
      <Link href="/" className="mt-2 text-sm font-medium text-brand hover:underline">
        Back to your bots
      </Link>
    </div>
  );
}
