import { Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import { ClockTime } from "@/components/time-ago";
import { useBot, useCurrentUser, useParticipantName } from "@/data/store";
import type { Message } from "@/data/types";
import { BotAvatar, MemberAvatar } from "@/features/bots/bot-avatar";
import { MessageActions } from "@/features/messages/message-actions";
import { MessageParts } from "@/features/messages/message-parts";
import { BudgetStopNotice } from "./budget-stop-notice";
import { LimitStopNotice, stoppedAtLimit } from "./limit-stop-notice";
import { SystemNotice } from "./system-notice";

/**
 * One message. Yours line up on the right; bots and teammates on the left.
 * In group chats every message from someone else shows who wrote it; in a DM, so does a guest's
 * (another bot pulled in with an @mention, ADR 0009). Notes from BotDesk itself are a status line.
 */
export function MessageItem({ message, isGroup, dmBotId }: { message: Message; isGroup: boolean; dmBotId?: string }) {
  const me = useCurrentUser();
  if (message.author.type === "system") return <SystemNotice message={message} />;
  const isOwn = message.author.type === "user" && message.author.id === me.id;
  const isGuest = !isGroup && message.author.type === "bot" && dmBotId !== undefined && message.author.id !== dmBotId;
  const showAuthor = (isGroup || isGuest) && !isOwn;
  const isThinking = message.status === "streaming" && message.parts.every((p) => p.type !== "text" || !p.text);

  return (
    <div className={cn("group/message flex gap-2.5", isOwn && "justify-end")}>
      {showAuthor && <AuthorAvatar author={message.author} />}

      <div className={cn("flex min-w-0 flex-1 flex-col gap-2", isOwn && "items-end")}>
        {showAuthor && <AuthorLine message={message} />}
        <MessageParts message={message} isOwn={isOwn} />
        {isThinking && <TypingDots />}
        {message.status === "error" &&
          (message.errorCode === "budget" ? (
            <BudgetStopNotice message={message} />
          ) : stoppedAtLimit(message) ? (
            <LimitStopNotice message={message} />
          ) : (
            <p className="text-xs text-destructive">{message.error ?? "This reply didn't finish."}</p>
          ))}
        {message.reactions?.length ? (
          <div className="flex gap-1">
            {message.reactions.map((r) => (
              <span key={r.emoji} className="rounded-full border bg-card px-2 py-0.5 text-xs">
                {r.emoji} {r.count}
              </span>
            ))}
          </div>
        ) : null}
        {message.readWhileWorking && (
          <p className="-mt-1 flex items-center gap-1 text-xs text-muted-foreground">
            <Zap aria-hidden className="size-3" /> Read while working
          </p>
        )}
        <MessageActions message={message} isOwn={isOwn} showTime={!showAuthor} />
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
