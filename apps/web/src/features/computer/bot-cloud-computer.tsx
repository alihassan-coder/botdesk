import { useEffect, useId } from "react";
import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { actions, useCloudComputer } from "@/data/store";
import type { Bot, CloudComputer } from "@/data/types";
import { computerStatusText, isChanging } from "@/lib/computer";
import { ComputerApps } from "./computer-apps";
import { ComputerScreen } from "./computer-screen";
import { ComputerStatus } from "./computer-status";
import { DeleteComputerButton } from "./delete-computer-button";

/** How often the computer's state is checked while it's on screen: bots start it, and it stops when idle. */
export const COMPUTER_CHECK_MS = 5_000;
/** While it's being made, started or stopped, it's checked this often instead. */
export const CHANGING_CHECK_MS = 1_500;

/**
 * A cloud bot's computer in its Computer tab (ADR 0020 §5): where it is, Start and Stop, Delete
 * computer, and while it runs its screen live, Take over, Open in Orgo, its apps and its previews.
 * The tab only mounts this while it's the open tab, so nothing is checked or fetched otherwise.
 */
export function BotCloudComputer({ bot }: { bot: Bot }) {
  const load = useCloudComputer(bot.id);
  const titleId = useId();
  const computer = load?.current;
  const changing = computer ? isChanging(computer.status) : false;

  useEffect(() => {
    void actions.loadComputer(bot.id);
    const check = () => {
      if (document.visibilityState === "visible") void actions.loadComputer(bot.id);
    };
    const timer = setInterval(check, changing ? CHANGING_CHECK_MS : COMPUTER_CHECK_MS);
    document.addEventListener("visibilitychange", check);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
    };
  }, [bot.id, changing]);

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-3">
      <div className="flex min-h-7 items-center justify-between gap-3">
        <h3 id={titleId} className="text-sm font-medium">Cloud computer</h3>
        {computer && computer.status !== "none" && <DeleteComputerButton bot={bot} disabled={changing} />}
      </div>

      {!computer ? (
        load?.status === "error" ? (
          <div role="alert" className="flex flex-col items-center gap-2 py-4 text-center text-sm text-destructive">
            {load.error}
            <Button size="sm" variant="outline" onClick={() => void actions.loadComputer(bot.id)}>Try again</Button>
          </div>
        ) : (
          <Skeleton className="h-16 rounded-xl" aria-label="Loading the cloud computer" />
        )
      ) : (
        <>
          <ComputerStatus bot={bot} computer={computer} />
          {computer.status === "running" ? <ComputerScreen bot={bot} /> : <NoScreen computer={computer} />}
          {computer.orgoUrl && (
            <a href={computer.orgoUrl} target="_blank" rel="noreferrer" className="inline-flex w-fit items-center gap-1 text-sm font-medium text-brand hover:underline">
              Open in Orgo <ExternalLink className="size-3.5" aria-hidden />
            </a>
          )}
          <ComputerApps computer={computer} />
        </>
      )}
    </section>
  );
}

/** Where the screen goes while there's none to show: starting, stopped, or not made yet. */
function NoScreen({ computer }: { computer: CloudComputer }) {
  if (computer.status === "none") return null;
  const changing = isChanging(computer.status);
  return (
    <div className="grid aspect-[16/10] place-items-center rounded-xl border border-dashed bg-muted/40 text-sm text-muted-foreground">
      <span className="flex items-center gap-2">
        {changing && <Spinner className="size-3.5 motion-reduce:animate-none" aria-hidden />}
        {computer.status === "error" ? "No screen to show" : computerStatusText(computer.status)}
      </span>
    </div>
  );
}
