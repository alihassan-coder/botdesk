import { useState } from "react";
import { Check, OctagonAlert, Square, X } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { actions, useBot, useRunsNeedingAttention, type ActionResult, type ActiveRun } from "@/data/store";

/**
 * A run that stopped because a tool may have half run (say, an email whose answer was lost).
 * A person checks and says what happened: It was done, or It wasn't done. The bot carries on
 * with that answer and never repeats the call by itself (ADR 0004 §2). Or Stop.
 */
export function RunAttentionNotices({ threadId }: { threadId: string }) {
  const runs = useRunsNeedingAttention(threadId);
  return runs.map((run) => <RunAttentionNotice key={run.id} run={run} />);
}

type Sending = "done" | "not_done" | "stop";

function RunAttentionNotice({ run }: { run: ActiveRun }) {
  const bot = useBot(run.botId);
  const [sending, setSending] = useState<Sending | null>(null);
  const busy = sending !== null;

  async function send(what: Sending, action: () => Promise<ActionResult>) {
    setSending(what);
    const result = await action();
    setSending(null);
    if (!result.ok) toast.error(result.error);
  }

  const resolve = (outcome: "done" | "not_done") => send(outcome, () => actions.resolveRun(run.id, outcome));

  return (
    <Alert variant="destructive" className="max-w-[560px]">
      <OctagonAlert />
      <AlertTitle>{bot?.name ?? "This bot"} needs a person to check</AlertTitle>
      <AlertDescription>{run.error ?? "Something may have only half happened."}</AlertDescription>
      <div className="col-start-2 mt-2 flex flex-wrap gap-2">
        <Button size="sm" onClick={() => resolve("done")} disabled={busy}>
          {sending === "done" ? <Spinner /> : <Check />} It was done
        </Button>
        <Button size="sm" variant="outline" onClick={() => resolve("not_done")} disabled={busy}>
          {sending === "not_done" ? <Spinner /> : <X />} It wasn&apos;t done
        </Button>
      </div>
      <AlertAction>
        <Button size="sm" variant="outline" onClick={() => send("stop", () => actions.stopRun(run.id))} disabled={busy}>
          {sending === "stop" ? <Spinner /> : <Square className="fill-current" />} Stop
        </Button>
      </AlertAction>
    </Alert>
  );
}
