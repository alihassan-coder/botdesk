import { useState } from "react";
import { OctagonAlert, Square } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { actions, useBot, useRunsNeedingAttention, type ActiveRun } from "@/data/store";

/**
 * A run that stopped because a tool may have half run (say, the API restarted mid-call).
 * A person must check what happened; for now the only way on is Stop.
 */
export function RunAttentionNotices({ threadId }: { threadId: string }) {
  const runs = useRunsNeedingAttention(threadId);
  return runs.map((run) => <RunAttentionNotice key={run.id} run={run} />);
}

function RunAttentionNotice({ run }: { run: ActiveRun }) {
  const bot = useBot(run.botId);
  const [isStopping, setIsStopping] = useState(false);

  async function stop() {
    setIsStopping(true);
    const result = await actions.stopRun(run.id);
    setIsStopping(false);
    if (!result.ok) toast.error(result.error);
  }

  return (
    <Alert variant="destructive" className="max-w-[560px]">
      <OctagonAlert />
      <AlertTitle>{bot?.name ?? "This bot"} needs a person to check</AlertTitle>
      <AlertDescription>{run.error ?? "Something may have only half happened."}</AlertDescription>
      <AlertAction>
        <Button size="sm" variant="outline" onClick={stop} disabled={isStopping}>
          {isStopping ? <Spinner /> : <Square className="fill-current" />} Stop
        </Button>
      </AlertAction>
    </Alert>
  );
}
