import { cn } from "@/lib/utils";
import { ClockTime } from "@/components/time-ago";
import { useBot, useCurrentUser, useParticipantName } from "@/data/store";
import type { Message } from "@/data/types";
import { BotAvatar, MemberAvatar } from "@/features/bots/bot-avatar";
import { MessageParts } from "@/features/messages/message-parts";

/**
 * One message. Yours line up on the right; bots and teammates on the left.
 * In group chats every message from someone else shows who wrote it.
 */
export function MessageItem({ message, isGroup }: { message: Message; isGroup: boolean }) {
  const me = useCurrentUser();
  const isOwn = message.author.type === "user" && message.author.id === me.id;
  const showAuthor = isGroup && !isOwn;
  const isThinking = message.status === "streaming" && message.parts.every((p) => p.type !== "text" || !p.text);

  return (
    <div className={cn("flex gap-2.5", isOwn && "justify-end")}>
      {showAuthor && <AuthorAvatar author={message.author} />}

      <div className={cn("flex min-w-0 flex-1 flex-col gap-2", isOwn && "items-end")}>
        {showAuthor && <AuthorLine message={message} />}
        <MessageParts message={message} isOwn={isOwn} />
        {isThinking && <TypingDots />}
        {message.reactions?.length ? (
          <div className="flex gap-1">
            {message.reactions.map((r) => (
              <span key={r.emoji} className="rounded-full border bg-card px-2 py-0.5 text-xs">
                {r.emoji} {r.count}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function AuthorAvatar({ author }: { author: Message["author"] }) {
  const bot = useBot(author.type === "bot" ? author.id : undefined);
  const name = useParticipantName(author);
  return bot ? <BotAvatar name={bot.name} color={bot.avatarColor} size="sm" className="mt-0.5" /> : <MemberAvatar name={name} size="sm" className="mt-0.5" />;
}

function AuthorLine({ message }: { message: Message }) {
  const name = useParticipantName(message.author);
  return (
    <p className="text-xs">
      <span className="font-semibold">{name}</span>
      <ClockTime iso={message.createdAt} className="ml-2 text-muted-foreground" />
    </p>
  );
}

/** Shown while a bot is thinking and hasn't written any words yet. */
function TypingDots() {
  return (
    <span className="flex w-fit gap-1 rounded-2xl bg-muted px-3.5 py-3" aria-label="Typing">
      {[0, 150, 300].map((delay) => (
        <span key={delay} className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60" style={{ animationDelay: `${delay}ms` }} />
      ))}
    </span>
  );
}
