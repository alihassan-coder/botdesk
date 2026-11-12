import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { useBot } from "@/data/store";
import type { Thread } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";

/**
 * Where messages and the composer go, while chats aren't on the API yet.
 * The header and details still work, so you can edit or remove the bot.
 */
export function ChatComingSoon({ thread }: { thread: Thread }) {
  const bot = useBot(thread.botId);
  const name = bot?.name ?? thread.title;

  return (
    <Empty className="p-8">
      <EmptyHeader>
        {bot && (
          <EmptyMedia>
            <BotAvatar name={bot.name} color={bot.avatarColor} size="lg" />
          </EmptyMedia>
        )}
        <EmptyTitle>Chat with {name} is coming soon</EmptyTitle>
        <EmptyDescription>
          {name} is on your team and ready. Talking to bots arrives in the next update. Meanwhile you can change
          its details and limits.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}
