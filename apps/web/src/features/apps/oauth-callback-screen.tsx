"use client";

import { useEffect } from "react";
import Link from "next/link";
import { CircleCheck, CircleX, ListChecks } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { actions, useAuthStatus, useMcpServers } from "@/data/store";
import { PageHeader } from "@/features/shell/page-header";
import { callbackOutcome } from "@/lib/connections";
import { waitingLabel } from "@/lib/mcp-review";

/**
 * Where the browser lands after signing in with an app's provider. The API has already saved
 * (or refused) the connection; this page only says how it went and leads back to Connect apps.
 */
export function OAuthCallbackScreen({ result, code, connector }: { result: string | null; code: string | null; connector: string | null }) {
  const outcome = callbackOutcome(result, code, connector);
  const mcp = outcome.ok && outcome.connectorId?.startsWith("mcp-") ? outcome.connectorId : null;

  useEffect(() => {
    if (outcome.ok) toast.success("Connected", { id: "oauth-connected" }); // an id, so a second effect run shows one toast
  }, [outcome.ok]);

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Connect apps" />
      <div className="mx-auto flex w-full max-w-xl flex-col gap-4 p-4 md:p-8">
        {mcp ? (
          <McpSignedIn pluginId={mcp} />
        ) : outcome.ok ? (
          <Alert>
            <CircleCheck />
            <AlertTitle>Connected</AlertTitle>
            <AlertDescription>The account is connected. Turn it on for a bot in the bot&apos;s Tools tab.</AlertDescription>
          </Alert>
        ) : (
          <Alert variant="destructive">
            <CircleX />
            <AlertTitle>Not connected</AlertTitle>
            <AlertDescription>{outcome.message}</AlertDescription>
          </Alert>
        )}
        <Button asChild className="self-start" variant={mcp ? "outline" : "default"}>
          <Link href="/apps">Back to Connect apps</Link>
        </Button>
      </div>
    </div>
  );
}

/** An MCP server's sign-in worked: its tools are listed now, and wait for the review (ADR 0012 §4). */
function McpSignedIn({ pluginId }: { pluginId: string }) {
  const signedIn = useAuthStatus() === "signed-in";
  const server = useMcpServers().items.find((s) => s.pluginId === pluginId);
  const waiting = server ? waitingLabel(server.tools) : null;

  useEffect(() => {
    if (signedIn) void actions.loadMcpServers();
  }, [signedIn]);

  return (
    <>
      <Alert>
        <CircleCheck />
        <AlertTitle>Signed in{server ? ` to ${server.name}` : ""}</AlertTitle>
        <AlertDescription>
          {waiting ? `${waiting}. ` : ""}No bot gets this MCP server&apos;s tools until an owner or admin has reviewed them, and it&apos;s on in the bot&apos;s Tools.
        </AlertDescription>
      </Alert>
      {server && (
        <Button asChild className="self-start">
          <Link href={`/apps/mcp/${server.id}`}><ListChecks /> Review tools</Link>
        </Button>
      )}
    </>
  );
}
