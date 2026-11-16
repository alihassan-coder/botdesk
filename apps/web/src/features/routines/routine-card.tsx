import { CalendarClock, ChevronRight, Clock, MessageSquare, MousePointerClick, PenLine, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { formatInZone, pluralize } from "@/lib/format";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Switch } from "@/components/ui/switch";
import { TimeAgo } from "@/components/time-ago";
import { actions, useBot, useCurrentUser } from "@/data/store";
import type { Routine, User } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { RoutineActions } from "./routine-actions";

const SOURCE = {
  recording: { label: "Recorded by watching you", icon: MousePointerClick },
  chat: { label: "Made from a chat", icon: MessageSquare },
  edit: { label: "Written by hand", icon: PenLine },
};

const OUTCOME = {
  success: { label: "Last run worked", className: "text-success" },
  failed: { label: "Last run failed", className: "text-destructive" },
  "needs-approval": { label: "Last run is waiting for approval", className: "text-brand" },
  running: { label: "Running now", className: "text-foreground" },
  skipped: { label: "Last slot skipped (the run before was still going, or a budget ran out)", className: "text-muted-foreground" },
};

/** Switch a routine on or off, saying so if the API refuses. */
export async function toggle(routine: Routine) {
  const result = await actions.toggleRoutine(routine.id);
  if (!result.ok) toast.error(result.error);
}

/** Its creator, owners and admins may switch a routine on or off and delete it (demo routines have no creator: anyone). */
export const canChangeRoutine = (routine: Routine, me: Pick<User, "id" | "role">) =>
  me.role !== "member" || !routine.createdBy || routine.createdBy === me.id;

/** Only its creator edits it or runs it now: its runs act for them. */
export const canEditRoutine = (routine: Routine, me: Pick<User, "id">) => !routine.createdBy || routine.createdBy === me.id;

/** One routine: who runs it, when, how the last run went, and (for who may change it) its actions. */
export function RoutineCard({ routine }: { routine: Routine }) {
  const bot = useBot(routine.botId);
  const me = useCurrentUser();
  const source = SOURCE[routine.source];
  const canChange = canChangeRoutine(routine, me);

  return (
    <article className={cn("rounded-2xl border bg-card p-5", !routine.enabled && "bg-muted/40")} aria-label={routine.name}>
      <div className="flex items-start gap-3">
        {bot && <BotAvatar name={bot.name} color={bot.avatarColor} />}
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold tracking-tight">{routine.name}</h3>
          {routine.instructionsHidden ? (
            <p className="text-sm text-muted-foreground italic">Only its creator, owners and admins see what it does.</p>
          ) : (
            <p className="line-clamp-3 text-sm whitespace-pre-line text-muted-foreground">{routine.description}</p>
          )}
        </div>
        <Switch
          checked={routine.enabled}
          onCheckedChange={() => void toggle(routine)}
          disabled={!canChange || !routine.botId}
          aria-label={`Run ${routine.name}`}
        />
      </div>

      {routine.disabledReason && !routine.enabled && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-destructive">
          <TriangleAlert className="size-3.5" /> Switched off: {routine.disabledReason}
        </p>
      )}

      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <CalendarClock className="size-3.5" /> {routine.schedule}
          {routine.timezone && <span>({routine.timezone})</span>}
        </span>
        {routine.nextRunAt && routine.timezone && routine.enabled && (
          <span className="flex items-center gap-1.5">
            <Clock className="size-3.5" /> Next: {formatInZone(routine.nextRunAt, routine.timezone)}
          </span>
        )}
        {!routine.cron && <span className="flex items-center gap-1.5"><source.icon className="size-3.5" /> {source.label}</span>}
        <span>{bot ? `Run by ${bot.name}` : "Its bot was removed"}</span>
        {routine.lastOutcome && routine.lastRunAt && (
          <span className={OUTCOME[routine.lastOutcome].className}>
            {OUTCOME[routine.lastOutcome].label} · <TimeAgo iso={routine.lastRunAt} />
          </span>
        )}
      </div>

      {routine.steps.length > 0 && (
        <Collapsible className="group/steps mt-3">
          <CollapsibleTrigger className="tap-target flex items-center gap-1 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground">
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
      )}

      {canChange && (
        <div className="mt-4 border-t pt-3">
          <RoutineActions routine={routine} canEdit={canEditRoutine(routine, me)} />
        </div>
      )}
    </article>
  );
}
