import { useBot } from "@/data/store";
import type { Thread } from "@/data/types";
import { BotDetails } from "./bot-details";
import { GroupMembers } from "./group-members";

export const PANE_MIN = 280;
export const PANE_MAX = 480;

/** What goes in the details pane: the bot's profile for a DM, the member list for a group. */
export function DetailsContent({ thread }: { thread: Thread }) {
  const bot = useBot(thread.botId);
  return bot ? <BotDetails bot={bot} /> : <GroupMembers thread={thread} />;
}

/**
 * Desktop only: the pane beside the chat. Drag its left edge to resize (280–480px);
 * the width is remembered by the parent.
 */
export function DetailsPane({ thread, width, onResize }: { thread: Thread; width: number; onResize: (width: number) => void }) {
  function startResize(e: React.PointerEvent) {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = width;

    const move = (ev: PointerEvent) => onResize(Math.min(PANE_MAX, Math.max(PANE_MIN, startWidth + (startX - ev.clientX))));
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  }

  return (
    <aside style={{ width }} className="relative hidden shrink-0 border-l xl:flex xl:flex-col" aria-label="Details">
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize details"
        onPointerDown={startResize}
        className="absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize hover:bg-ring/30"
      />
      <DetailsContent thread={thread} />
    </aside>
  );
}
