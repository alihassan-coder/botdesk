import { useId, useState } from "react";
import Link from "next/link";
import { ArrowRight, ChevronDown, CornerDownRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useBot } from "@/data/store";
import type { Bot, HandoffPart as HandoffPartData } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { EditBotDialog } from "@/features/bots/edit-bot-dialog";
import { plainPreview } from "@/lib/tasks";
import { cn } from "@/lib/utils";
import { PartCard } from "./part-card";
import { TaskStatusBadge } from "./task-status-badge";

/**
 * One bot handing a Task to a teammate (ADR 0014): who to whom, the Task, and where it is.
 * The card changes in place as the Task moves on. Its status sits in a polite live region, so a
 * screen reader hears "Sales Outbound's task: Done" when it happens. Once done, the result's
 * preview folds open and "View reply" jumps to the teammate's reply in the chat.
 */
export function HandoffPart({ part }: { part: HandoffPartData }) {
  const from = useBot(part.fromBotId);
  const to = useBot(part.toBotId);
  const headingId = useId();
  const toName = to?.name ?? "a removed bot";
  const ended = part.status === "failed" || part.status === "cancelled";

  return (
    <PartCard role="article" aria-labelledby={headingId} className={cn("flex flex-col gap-2", part.status === "failed" && "border-destructive/30")}>
      <div className="flex items-start justify-between gap-3">
        <h3
          id={headingId}
          className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-[13px]"
          aria-label={`${from?.name ?? "A removed bot"} handed a task to ${toName}`}
        >
          <BotName bot={from} />
          {/* The arrow wraps with the teammate, so a narrow card reads "Chief" / "→ Sales Outbound". */}
          <span className="flex min-w-0 items-center gap-1.5">
            <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
            <BotName bot={to} showHandle />
          </span>
        </h3>
        <span aria-live="polite" aria-atomic="true" className="shrink-0">
          <span className="sr-only">{toName}&apos;s task: </span>
          <TaskStatusBadge status={part.status} />
        </span>
      </div>

      <p className="text-pretty text-foreground/90">{part.task}</p>

      {part.status === "done" && <TaskResult part={part} />}
      {ended && part.error && <TaskError part={part} owner={to} />}
    </PartCard>
  );
}

function BotName({ bot, showHandle = false }: { bot: Bot | undefined; showHandle?: boolean }) {
  if (!bot) return <span className="text-muted-foreground">A removed bot</span>;
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <BotAvatar name={bot.name} color={bot.avatarColor} size="sm" />
      <span className="truncate font-medium">{bot.name}</span>
      {showHandle && <span className="text-muted-foreground">@{bot.handle}</span>}
    </span>
  );
}

/** The result's first lines, folded away by default (the full reply is right below in the chat). */
function TaskResult({ part }: { part: HandoffPartData }) {
  const [open, setOpen] = useState(false);
  if (!part.resultPreview && !part.resultMessageId) return null;
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-xl bg-muted/60 text-[13px]">
      <div className="flex items-center justify-between gap-2 px-1 py-0.5">
        {part.resultPreview ? (
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-muted-foreground">
              <ChevronDown
                className={cn("size-3.5 transition-transform duration-200 ease-out motion-reduce:transition-none", open && "rotate-180")}
              />
              {open ? "Hide result" : "Show result"}
            </Button>
          </CollapsibleTrigger>
        ) : (
          <span />
        )}
        {part.resultMessageId && (
          <Button variant="ghost" size="sm" className="h-7 gap-1 px-2" onClick={() => showMessage(part.resultMessageId!)}>
            <CornerDownRight className="size-3.5" /> View reply
          </Button>
        )}
      </div>
      <CollapsibleContent className="px-3 pb-3 text-muted-foreground">{plainPreview(part.resultPreview ?? "")}</CollapsibleContent>
    </Collapsible>
  );
}

/** Why it didn't finish. Out of budget offers the way to raise it, as a reply that hit its budget does. */
function TaskError({ part, owner }: { part: HandoffPartData; owner?: Bot }) {
  return (
    <div className="flex flex-col gap-2 text-[13px]">
      <p className={part.status === "failed" ? "text-destructive" : "text-muted-foreground"}>{part.error}</p>
      {part.errorCode === "budget" && (
        <div className="flex flex-wrap gap-2">
          {owner && <EditBotDialog bot={owner} />}
          <Button asChild variant="ghost" size="sm">
            <Link href="/settings/usage">Usage &amp; budgets</Link>
          </Button>
        </div>
      )}
    </div>
  );
}

/** Scrolls the chat to a message and moves focus there, so keyboard and screen-reader users land on it too. */
function showMessage(messageId: string) {
  const target = document.getElementById(`message-${messageId}`);
  if (!target) return;
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  target.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
  target.focus({ preventScroll: true });
}
