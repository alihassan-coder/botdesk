import { useEffect, useId } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { actions, useBotBrowser, useIsDemo } from "@/data/store";
import type { Bot } from "@/data/types";
import { ForgetSignInsButton } from "./forget-sign-ins-button";
import { LiveView } from "./live-view";
import { OpenPageForm } from "./open-page-form";

/** How often the browser's state is checked while it's on screen: bots open, browse and close it on their own. */
export const BROWSER_CHECK_MS = 5_000;

/**
 * A bot's Browser (its Computer tab, ADR 0017 §5): not available here, closed (open a page to
 * start it), or open, with a live picture and Take over. Forget sign-ins clears its profile.
 */
export function BotBrowser({ bot }: { bot: Bot }) {
  const load = useBotBrowser(bot.id);
  const isDemo = useIsDemo();
  const titleId = useId();

  useEffect(() => {
    void actions.loadBrowser(bot.id);
    const check = () => {
      if (document.visibilityState === "visible") void actions.loadBrowser(bot.id);
    };
    const timer = setInterval(check, BROWSER_CHECK_MS);
    document.addEventListener("visibilitychange", check);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
    };
  }, [bot.id]);

  const browser = load?.current;

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-3">
      <div className="flex min-h-7 items-center justify-between gap-3">
        <h3 id={titleId} className="text-sm font-medium">Browser</h3>
        {browser?.available && <ForgetSignInsButton bot={bot} />}
      </div>

      {!browser ? (
        load?.status === "error" ? (
          <div role="alert" className="flex flex-col items-center gap-2 py-4 text-center text-sm text-destructive">
            {load.error}
            <Button size="sm" variant="outline" onClick={() => void actions.loadBrowser(bot.id)}>Try again</Button>
          </div>
        ) : (
          <Skeleton className="h-16 rounded-xl" aria-label="Loading the browser" />
        )
      ) : !browser.available ? (
        <p className="text-sm text-muted-foreground">
          {isDemo ? "Not available in the demo." : "Watching the browser isn't available on this server."}
        </p>
      ) : browser.open ? (
        <LiveView bot={bot} browser={browser} />
      ) : (
        <div className="flex flex-col gap-3 rounded-xl border border-dashed p-3">
          <OpenPageForm bot={bot} label="Open a page" />
          <p className="text-xs text-pretty text-muted-foreground">
            Bots never type passwords. When a bot asks you to sign in somewhere, open the site here, take over and sign in; the bot keeps the sign-in.
          </p>
        </div>
      )}
    </section>
  );
}
