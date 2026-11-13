"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCheck, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TimeAgo } from "@/components/time-ago";
import { actions, useApprovals, useAuthStatus, useBot, useBots, useOrg, useThread } from "@/data/store";
import type { Approval } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { PageHeader } from "@/features/shell/page-header";
import { ApprovalCard } from "./approval-card";

const ALL_BOTS = "all";

/** /approvals — every action waiting for a yes, from every bot, in one place; and past decisions. */
export function ApprovalsScreen() {
  const approvals = useApprovals();
  const bots = useBots();
  const [botId, setBotId] = useState(ALL_BOTS);
  const { isLoading, error, retry } = useLoadApprovals();

  const shown = botId === ALL_BOTS ? approvals : approvals.filter((a) => a.botId === botId);
  const waiting = shown.filter((a) => a.status === "pending");
  const decided = shown.filter((a) => a.status !== "pending");

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Approvals" />
      <div className="flex-1 overflow-y-auto">
        <Tabs defaultValue="waiting" className="mx-auto max-w-2xl gap-6 p-4 md:p-8">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Approvals</h2>
            <p className="mt-1 text-sm text-muted-foreground">Bots stop and ask before anything risky. Nothing happens until someone decides.</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <TabsList>
              <TabsTrigger value="waiting">Waiting{isLoading ? "" : ` · ${waiting.length}`}</TabsTrigger>
              <TabsTrigger value="decided">Decided{isLoading ? "" : ` · ${decided.length}`}</TabsTrigger>
            </TabsList>
            <Select value={botId} onValueChange={setBotId}>
              <SelectTrigger className="ml-auto w-44" aria-label="Filter by bot">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_BOTS}>All bots</SelectItem>
                {bots.map((bot) => (
                  <SelectItem key={bot.id} value={bot.id}>{bot.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <TabsContent value="waiting" className="flex flex-col gap-6">
            {isLoading ? (
              <Loading />
            ) : error ? (
              <LoadFailed error={error} onRetry={retry} />
            ) : waiting.length > 0 ? (
              waiting.map((a) => <ApprovalEntry key={a.id} approval={a} />)
            ) : (
              <AllCaughtUp />
            )}
          </TabsContent>
          <TabsContent value="decided" className="flex flex-col gap-6">
            {isLoading ? (
              <Loading />
            ) : error ? (
              <LoadFailed error={error} onRetry={retry} />
            ) : decided.length > 0 ? (
              decided.map((a) => <ApprovalEntry key={a.id} approval={a} />)
            ) : (
              <p className="py-16 text-center text-sm text-muted-foreground">Nothing decided yet.</p>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

/**
 * The page asks for the newest approvals when it opens, and again when you switch organization
 * (the mock has them all). Until then it shows a spinner, on the server too, so the server's
 * HTML matches the browser's first render. A failed load says so, with Retry, rather than
 * looking like there's nothing to decide.
 */
function useLoadApprovals() {
  const authStatus = useAuthStatus();
  const orgId = useOrg().id;
  const [attempt, setAttempt] = useState(0);
  /** Which load (org and attempt) the last answer was for, so a new one shows the spinner again. */
  const key = `${orgId}:${attempt}`;
  const [answer, setAnswer] = useState<{ key: string; error: string | null } | null>(null);
  useEffect(() => {
    if (authStatus !== "signed-in") return;
    let current = true;
    void actions.loadApprovals().then((result) => {
      if (current) setAnswer({ key, error: result.ok ? null : result.error });
    });
    return () => {
      current = false;
    };
  }, [authStatus, key]);
  const isLoading = answer?.key !== key;
  return {
    isLoading: isLoading && authStatus !== "signed-out",
    error: isLoading ? null : (answer?.error ?? null),
    retry: () => setAttempt((n) => n + 1),
  };
}

function LoadFailed({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-2 py-16 text-center" role="alert">
      <TriangleAlert className="size-8 text-destructive" />
      <p className="font-medium">Couldn&apos;t load approvals</p>
      <p className="text-sm text-muted-foreground">{error}</p>
      <Button size="sm" variant="outline" className="mt-2" onClick={onRetry}>Try again</Button>
    </div>
  );
}

function Loading() {
  return (
    <div className="flex justify-center py-16" aria-busy="true">
      <Spinner className="size-5 text-muted-foreground" />
      <span className="sr-only">Loading approvals…</span>
    </div>
  );
}

function AllCaughtUp() {
  return (
    <div className="flex flex-col items-center gap-2 py-16 text-center">
      <CheckCheck className="size-8 text-success" />
      <p className="font-medium">You&apos;re all caught up</p>
      <p className="text-sm text-muted-foreground">New requests from your bots will show up here.</p>
    </div>
  );
}

/** One request: which bot asked, in which chat, when; then the card itself. */
function ApprovalEntry({ approval }: { approval: Approval }) {
  const bot = useBot(approval.botId);
  const thread = useThread(approval.threadId);

  return (
    <article className="flex flex-col gap-2" aria-label={approval.title}>
      <div className="flex items-center gap-2 text-sm">
        {bot && <BotAvatar name={bot.name} color={bot.avatarColor} size="sm" />}
        <span className="font-medium">{bot?.name ?? "A removed bot"}</span>
        {thread && (
          <>
            <span className="text-muted-foreground">in</span>
            <Link href={`/chat/${approval.threadId}`} className="truncate text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
              {thread.kind === "dm" ? "your chat" : thread.title}
            </Link>
          </>
        )}
        <TimeAgo iso={approval.requestedAt} className="ml-auto shrink-0 text-xs text-muted-foreground" />
      </div>
      <ApprovalCard approvalId={approval.id} />
    </article>
  );
}
