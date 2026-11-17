import { useBot } from "@/data/store";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { botWelcome } from "@/lib/bot-welcome";

/**
 * An empty DM: the bot introduces itself, so a newly hired bot's chat never opens blank.
 * It isn't a saved message, just the chat's starting point.
 */
export function DmWelcome({ botId, title }: { botId: string; title: string }) {
  const bot = useBot(botId);
  if (!bot) return <p className="flex flex-1 items-center justify-center p-8 text-center text-sm text-muted-foreground">No messages yet. Say hi to {title}.</p>;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-end gap-3 px-4 py-6 md:px-6">
      <div className="flex items-end gap-2.5">
        <BotAvatar name={bot.name} color={bot.avatarColor} />
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">{bot.name}</span>
          <p className="w-fit max-w-prose rounded-2xl rounded-bl-md bg-muted px-3.5 py-2.5 text-sm text-pretty">{botWelcome(bot)}</p>
        </div>
      </div>
    </div>
  );
}
