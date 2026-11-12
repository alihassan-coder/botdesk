"use client";

import Link from "next/link";
import { CheckCheck } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TimeAgo } from "@/components/time-ago";
import { useApprovals, useBot, useThread } from "@/data/store";
import type { Approval } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { PageHeader } from "@/features/shell/page-header";
import { ApprovalCard } from "./approval-card";

/** /approvals — every action waiting for a yes, from every bot, in one place. */
export function ApprovalsScreen() {
  const approvals = useApprovals();
  const waiting = approvals.filter((a) => a.status === "pending");
  const decided = approvals.filter((a) => a.status !== "pending");

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Approvals" />
      <div className="flex-1 overflow-y-auto">
        <Tabs defaultValue="waiting" className="mx-auto max-w-2xl gap-6 p-4 md:p-8">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Approvals</h2>
            <p className="mt-1 text-sm text-muted-foreground">Bots stop and ask before anything risky. Nothing happens until someone decides.</p>
          </div>
          <TabsList>
            <TabsTrigger value="waiting">Waiting · {waiting.length}</TabsTrigger>
            <TabsTrigger value="decided">Decided · {decided.length}</TabsTrigger>
          </TabsList>

          <TabsContent value="waiting" className="flex flex-col gap-6">
            {waiting.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-16 text-center">
                <CheckCheck className="size-8 text-success" />
                <p className="font-medium">You&apos;re all caught up</p>
                <p className="text-sm text-muted-foreground">New requests from your bots will show up here.</p>
              </div>
            ) : (
              waiting.map((a) => <ApprovalEntry key={a.id} approval={a} />)
            )}
          </TabsContent>
          <TabsContent value="decided" className="flex flex-col gap-6">
            {decided.map((a) => (
              <ApprovalEntry key={a.id} approval={a} />
            ))}
          </TabsContent>
        </Tabs>
      </div>
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
        <span className="font-medium">{bot?.name}</span>
        <span className="text-muted-foreground">in</span>
        <Link href={`/chat/${approval.threadId}`} className="truncate text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
          {thread?.title}
        </Link>
        <TimeAgo iso={approval.requestedAt} className="ml-auto shrink-0 text-xs text-muted-foreground" />
      </div>
      <ApprovalCard approvalId={approval.id} />
    </article>
  );
}
