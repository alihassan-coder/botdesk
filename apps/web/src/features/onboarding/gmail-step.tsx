import { useEffect, useState } from "react";
import { ConnectorLogo } from "@/components/connector-logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { actions, useAccountConnections, useAuthStatus, useServerConnectors } from "@/data/store";
import { AccountConnectDialog } from "@/features/apps/account-connect-dialog";
import { GOOGLE_SETUP_GUIDE_URL } from "@/lib/connections";
import { StepFrame } from "./step-frame";

/**
 * Step 4: connect Gmail with the same dialog as Connect apps. Signing in with Google takes the
 * whole tab away (OAuth), so `onLeave` marks setup done when the dialog opens (cancelling it
 * still leaves you here, with Finish). A server without a Google client
 * says so, with the setup guide, and the step can be skipped.
 */
export function GmailStep({ onFinish, onLeave }: { onFinish: () => void; onLeave: () => void }) {
  const connectors = useServerConnectors();
  const accounts = useAccountConnections();
  const signedIn = useAuthStatus() === "signed-in";
  const [connecting, setConnecting] = useState(false);
  const gmail = connectors.items.find((c) => c.id === "gmail");
  const connected = accounts.items.some((a) => a.connectorId === "gmail" && a.status === "active");

  useEffect(() => {
    if (signedIn) void actions.loadConnections();
  }, [signedIn]);

  return (
    <StepFrame
      title="Connect Gmail"
      description="Let your bots read, sort and draft email. Anything risky, like sending, still waits for your approval."
      onSkip={onFinish}
      skipLabel="Skip for now"
      action={<Button onClick={onFinish}>Finish</Button>}
    >
      {connectors.status === "loading" && !gmail ? (
        <Skeleton className="h-24 rounded-2xl" />
      ) : connectors.status === "error" ? (
        <div className="flex items-center gap-3 rounded-2xl border border-dashed p-4 text-sm text-muted-foreground">
          <p className="flex-1">Couldn&apos;t load the apps.</p>
          <Button variant="outline" size="sm" onClick={() => void actions.loadConnections()}>Try again</Button>
        </div>
      ) : !gmail ? (
        <p className="rounded-2xl border border-dashed p-4 text-sm text-muted-foreground">
          Gmail isn&apos;t switched on for this server. You can connect apps later from Connect apps.
        </p>
      ) : (
        <div className="flex flex-col gap-3 rounded-2xl border p-4">
          <div className="flex items-center gap-3">
            <ConnectorLogo connectorId="gmail" name="Gmail" decorative />
            <p className="flex-1 font-medium">Gmail</p>
            {connected ? (
              <Badge>Connected</Badge>
            ) : gmail.setup === "not-configured" ? (
              <Badge variant="secondary">Not set up</Badge>
            ) : (
              <Button size="sm" onClick={() => { onLeave(); setConnecting(true); }}>Connect Gmail</Button>
            )}
          </div>
          {gmail.setup === "not-configured" && !connected && (
            <p className="text-sm text-muted-foreground">
              Not set up on this server: it needs a Google sign-in client first.{" "}
              <a className="font-medium text-foreground underline underline-offset-4" href={GOOGLE_SETUP_GUIDE_URL} target="_blank" rel="noreferrer">
                How to set it up
              </a>
            </p>
          )}
        </div>
      )}
      <AccountConnectDialog connector={connecting ? gmail ?? null : null} onClose={() => setConnecting(false)} />
    </StepFrame>
  );
}
