import { useState } from "react";
import { Play, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { ClockTime } from "@/components/time-ago";
import { actions } from "@/data/store";
import type { Bot, CloudComputer } from "@/data/types";
import { computerSpecs, computerStatusText, isChanging } from "@/lib/computer";
import { cn } from "@/lib/utils";

/**
 * Where a bot's cloud computer is (none yet, starting, running, stopped…), what it is, and Start or
 * Stop. Starting the first time makes it, which takes a while; the tab checks until it's done.
 * The API's refusal shows under it.
 */
export function ComputerStatus({ bot, computer }: { bot: Bot; computer: CloudComputer }) {
  const [busy, setBusy] = useState<"start" | "stop" | null>(null);
  const [error, setError] = useState("");
  const { status } = computer;
  const canStart = status === "none" || status === "stopped" || status === "error";
  const specs = computerSpecs(computer);

  async function change(what: "start" | "stop") {
    setBusy(what);
    setError("");
    const result = await (what === "start" ? actions.startComputer(bot.id) : actions.stopComputer(bot.id));
    setBusy(null);
    if (!result.ok) setError(result.error);
  }

  return (
    <div className="flex flex-col gap-2 rounded-xl border p-3">
      <div className="flex items-center gap-3">
        <StatusDot status={status} />
        <div className="min-w-0 flex-1" aria-live="polite" aria-atomic="true">
          <p className="text-sm font-medium">{computerStatusText(status)}</p>
          {specs && <p className="truncate text-xs text-muted-foreground">{specs}</p>}
        </div>
        {canStart ? (
          <Button size="sm" onClick={() => void change("start")} disabled={busy !== null}>
            {busy === "start" ? <Spinner className="motion-reduce:animate-none" /> : <Play />} {status === "error" ? "Try again" : "Start"}
          </Button>
        ) : status === "running" ? (
          <Button size="sm" variant="outline" onClick={() => void change("stop")} disabled={busy !== null}>
            {busy === "stop" ? <Spinner className="motion-reduce:animate-none" /> : <Square />} Stop
          </Button>
        ) : null}
      </div>
      <Detail bot={bot} computer={computer} />
      {error && <p role="alert" className="text-xs text-pretty text-destructive">{error}</p>}
    </div>
  );
}

function Detail({ bot, computer }: { bot: Bot; computer: CloudComputer }) {
  const line = "text-xs text-pretty text-muted-foreground";
  switch (computer.status) {
    case "none":
      return <p className={line}>Start makes one, or {bot.name} does when it needs it. Orgo bills your account while it runs.</p>;
    case "stopped":
      return <p className={line}>Its disk is kept: Start picks up where it left off.</p>;
    case "error":
      return <p className={cn(line, "text-destructive")}>{computer.error ?? "The computer didn't answer."}</p>;
    case "running":
      return computer.idleStopsAt ? <p className={line}>Stops at <ClockTime iso={computer.idleStopsAt} /> if nothing uses it before then.</p> : null;
    default:
      return null;
  }
}

/** Green when running, amber while it changes, red on an error, grey otherwise. Pulses only while it changes (and motion is welcome). */
function StatusDot({ status }: { status: CloudComputer["status"] }) {
  const changing = isChanging(status);
  return (
    <span aria-hidden className={cn(
      "size-2.5 shrink-0 rounded-full",
      status === "running" ? "bg-success" : changing ? "bg-working motion-safe:animate-pulse" : status === "error" ? "bg-destructive" : "bg-muted-foreground/40",
    )} />
  );
}
