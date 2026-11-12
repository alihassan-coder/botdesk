import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { TimeAgo } from "@/components/time-ago";
import { useBot } from "@/data/store";
import type { Thread } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";

/** Statuses worth showing instead of the last message, because they need you or explain silence. */
const SHOW_STATUS_TEXT = new Set(["working", "waiting-approval", "error", "sleeping"]);

/** One conversation in the list: avatar, name, time, one line of preview, unread count. */
export function ThreadRow({ thread, onNavigate }: { thread: Thread; onNavigate?: () => void }) {
  const isActive = usePathname() === `/chat/${thread.id}`;
  const bot = useBot(thread.botId);

  const preview = bot && SHOW_STATUS_TEXT.has(bot.status) && bot.statusText ? bot.statusText : thread.lastMessagePreview;
  const previewIsStatus = preview !== thread.lastMessagePreview;

  return (
    <Link
      href={`/chat/${thread.id}`}
      onClick={onNavigate}
      aria-current={isActive ? "page" : undefined}
      title={thread.title}
      className={cn(
        "flex items-center gap-3 rounded-[10px] px-2 py-2 outline-none transition-colors",
        "group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0",
        "hover:bg-sidebar-accent/70 focus-visible:ring-2 focus-visible:ring-ring",
        isActive && "bg-sidebar-accent",
      )}
    >
      {bot ? <BotAvatar name={bot.name} color={bot.avatarColor} status={bot.status} /> : <GroupAvatar thread={thread} />}

      <span className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden">
        <span className="flex items-baseline gap-2">
          <span className={cn("truncate text-sm", thread.unread ? "font-semibold" : "font-medium")}>{thread.title}</span>
          <TimeAgo iso={thread.lastMessageAt} className="ml-auto shrink-0 text-xs text-muted-foreground" />
        </span>
        <span className="flex items-center gap-2">
          <span className={cn("truncate text-xs", previewIsStatus && bot?.status === "waiting-approval" ? "text-brand" : "text-muted-foreground")}>
            {preview}
          </span>
          {thread.unread > 0 && (
            <span className="ml-auto grid h-[18px] min-w-[18px] shrink-0 place-items-center rounded-full bg-brand px-1 text-[11px] font-semibold text-brand-foreground">
              {thread.unread}
            </span>
          )}
        </span>
      </span>
    </Link>
  );
}

/** Group chats show their first two bots, overlapped. */
function GroupAvatar({ thread }: { thread: Thread }) {
  const botIds = thread.participants.filter((p) => p.type === "bot").map((p) => p.id);
  const first = useBot(botIds[0]);
  const second = useBot(botIds[1]);

  return (
    <span className="relative size-9 shrink-0">
      {first && <BotAvatar name={first.name} color={first.avatarColor} size="sm" className="absolute top-0 left-0" />}
      {second && (
        <BotAvatar name={second.name} color={second.avatarColor} size="sm" className="absolute right-0 bottom-0 rounded-md ring-2 ring-sidebar" />
      )}
    </span>
  );
}
