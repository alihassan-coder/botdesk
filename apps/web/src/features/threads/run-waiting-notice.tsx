import { useState } from "react";
import { Square, UsersRound } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { actions, useBot, useBots, useRunsWaitingOnTasks, useWaitedOnBots, type ActiveRun } from "@/data/store";

/**
 * A bot that handed Tasks to teammates and is waiting for them to finish (ADR 0014):
 * "Chief is waiting for @sales and @inbox". It carries on by itself once they're done;
 * Stop ends it and cancels the Tasks still open.
 */
export function RunWaitingNotices({ threadId }: { threadId: string }) {
  const runs = useRunsWaitingOnTasks(threadId);
  return runs.map((run) => <RunWaitingNotice key={run.id} run={run} />);
}

function RunWaitingNotice({ run }: { run: ActiveRun }) {
  const bot = useBot(run.botId);
  const bots = useBots();
  const waitedOn = useWaitedOnBots(run);
  const [isStopping, setIsStopping] = useState(false);
  const handles = waitedOn.map((id) => `@${bots.find((b) => b.id === id)?.handle ?? "a removed bot"}`);

  async function stop() {
    setIsStopping(true);
    const result = await actions.stopRun(run.id);
    setIsStopping(false);
    if (!result.ok) toast.error(result.error);
  }

  return (
    <div role="status" className="flex w-full max-w-[560px] items-center gap-3 rounded-2xl border border-dashed px-3.5 py-2.5 text-[13px]">
      <UsersRound className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      <p className="min-w-0 flex-1">
        <span className="font-medium">{bot?.name ?? "A bot"}</span> is waiting for{" "}
        {handles.length > 0 ? <span className="font-medium">{listOf(handles)}</span> : "its teammates"}
        <span className="block text-xs text-muted-foreground">It carries on when they&apos;ve finished.</span>
      </p>
      <Button size="sm" variant="outline" onClick={stop} disabled={isStopping} aria-label={`Stop ${bot?.name ?? "the bot"}`}>
        {isStopping ? <Spinner /> : <Square className="fill-current" />} Stop
      </Button>
    </div>
  );
}

/** "@a", "@a and @b", "@a, @b and @c". */
function listOf(items: string[]) {
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}
