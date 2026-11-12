import { CalendarClock, ChevronRight, MessageSquare, MousePointerClick, PenLine } from "lucide-react";
import { cn } from "@/lib/utils";
import { pluralize } from "@/lib/format";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Switch } from "@/components/ui/switch";
import { TimeAgo } from "@/components/time-ago";
import { actions, useBot } from "@/data/store";
import type { Routine } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";

const SOURCE = {
  recording: { label: "Recorded by watching you", icon: MousePointerClick },
  chat: { label: "Made from a chat", icon: MessageSquare },
  edit: { label: "Written by hand", icon: PenLine },
};

const OUTCOME = {
  success: { label: "Last run worked", className: "text-success" },
  failed: { label: "Last run failed", className: "text-destructive" },
  "needs-approval": { label: "Last run is waiting for approval", className: "text-brand" },
};

/** One routine: who runs it, when, how it was made, how the last run went, and its steps. */
export function RoutineCard({ routine }: { routine: Routine }) {
  const bot = useBot(routine.botId);
  const source = SOURCE[routine.source];

  return (
    <article className={cn("rounded-2xl border bg-card p-5 transition-opacity", !routine.enabled && "opacity-60")} aria-label={routine.name}>
      <div className="flex items-start gap-3">
        {bot && <BotAvatar name={bot.name} color={bot.avatarColor} />}
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold tracking-tight">{routine.name}</h3>
          <p className="text-sm text-muted-foreground">{routine.description}</p>
        </div>
        <Switch checked={routine.enabled} onCheckedChange={() => actions.toggleRoutine(routine.id)} aria-label={`Run ${routine.name}`} />
      </div>

      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5"><CalendarClock className="size-3.5" /> {routine.schedule}</span>
        <span className="flex items-center gap-1.5"><source.icon className="size-3.5" /> {source.label}</span>
        {bot && <span>Run by {bot.name}</span>}
        {routine.lastOutcome && routine.lastRunAt && (
          <span className={OUTCOME[routine.lastOutcome].className}>
            {OUTCOME[routine.lastOutcome].label} · <TimeAgo iso={routine.lastRunAt} />
          </span>
        )}
      </div>

      <Collapsible className="group/steps mt-3">
        <CollapsibleTrigger className="flex items-center gap-1 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground">
          <ChevronRight className="size-3.5 transition-transform group-data-[state=open]/steps:rotate-90" /> {pluralize(routine.steps.length, "step")}
        </CollapsibleTrigger>
        <CollapsibleContent>
          <ol className="mt-2 flex flex-col gap-1.5 border-l pl-4 text-sm">
            {routine.steps.map((step, i) => (
              <li key={i} className="flex gap-2">
                <span className="w-4 shrink-0 text-muted-foreground">{i + 1}.</span> {step}
              </li>
            ))}
          </ol>
        </CollapsibleContent>
      </Collapsible>
    </article>
  );
}
