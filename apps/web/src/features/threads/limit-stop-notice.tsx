import { Play } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { actions, useBot, useThread } from "@/data/store";
import type { Message } from "@/data/types";

const LIMIT = /reached its (?:time )?limit/i;
export const CONTINUE = "Continue where you left off.";

/** A reply that stopped because its run used all its steps or its time (also known after a reload, by its words). */
export function stoppedAtLimit(message: Message): boolean {
  return message.status === "error" && (message.errorCode === "limit" || LIMIT.test(message.error ?? ""));
}

/**
 * Says the bot stopped at its limit, not because something broke, and offers to carry on: Continue
 * sends "Continue where you left off." (to the bot by name in a group), which starts a fresh run
 * that reads the chat so far.
 */
export function LimitStopNotice({ message }: { message: Message }) {
  const bot = useBot(message.author.type === "bot" ? message.author.id : undefined);
  const thread = useThread(message.threadId);
  const text = thread?.kind === "group" && bot ? `@${bot.handle} ${CONTINUE}` : CONTINUE;

  return (
    <Alert className="max-w-[560px]">
      <Play />
      <AlertTitle>{bot ? `${bot.name} stopped at its limit` : "Stopped at its limit"}</AlertTitle>
      <AlertDescription>
        <p>{message.error} Nothing went wrong: a run gets a set number of steps and minutes, and this job needed more.</p>
        <div className="mt-2">
          <Button size="sm" onClick={() => actions.sendMessage(message.threadId, text)}>
            Continue
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  );
}
