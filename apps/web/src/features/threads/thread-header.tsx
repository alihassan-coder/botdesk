import Link from "next/link";
import { ArrowLeft, PanelRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useBot } from "@/data/store";
import type { Thread } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { BOT_STATUS } from "@/features/bots/bot-status";

/** Top of a chat: back (phones), who you're talking to and what they're doing, details toggle. */
export function ThreadHeader({ thread, onToggleDetails }: { thread: Thread; onToggleDetails: () => void }) {
  const bot = useBot(thread.botId);
  const memberCount = thread.participants.length;

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b px-3 md:px-4">
      <Button asChild variant="ghost" size="icon-sm" className="md:hidden" aria-label="Back to bots">
        <Link href="/">
          <ArrowLeft />
        </Link>
      </Button>

      {bot && <BotAvatar name={bot.name} color={bot.avatarColor} size="sm" />}
      <div className="min-w-0">
        <h1 className="truncate text-sm font-semibold">{thread.title}</h1>
        <p className="truncate text-xs text-muted-foreground">
          {bot ? (bot.statusText ?? BOT_STATUS[bot.status].label) : `${memberCount} members`}
        </p>
      </div>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon-sm" className="ml-auto" onClick={onToggleDetails} aria-label="Details">
            <PanelRight />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Details</TooltipContent>
      </Tooltip>
    </header>
  );
}
