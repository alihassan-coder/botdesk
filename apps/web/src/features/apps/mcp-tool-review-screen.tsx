"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { actions, useAuthStatus, useCurrentUser, useMcpServers, useOrg } from "@/data/store";
import type { McpServer, McpToolChoice } from "@/data/types";
import { PageHeader } from "@/features/shell/page-header";
import { initialChoices, reviewOrder } from "@/lib/mcp-review";
import { McpToolReviewItem } from "./mcp-tool-review-item";

/**
 * Connect apps → an MCP server → Review tools (ADR 0012 §4-§5). Each tool's description and
 * arguments; owners and admins choose which are offered to bots and at what risk, and approve
 * changed and new tools (nothing changed works again until they do). Members can look.
 */
export function McpToolReviewScreen({ serverId }: { serverId: string }) {
  const servers = useMcpServers();
  const signedIn = useAuthStatus() === "signed-in";
  const orgId = useOrg().id;
  const server = servers.items.find((s) => s.id === serverId);

  useEffect(() => {
    if (signedIn) void actions.loadMcpServers();
  }, [signedIn, orgId]);

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Review tools">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/apps"><ArrowLeft /> Connect apps</Link>
        </Button>
      </PageHeader>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 overflow-y-auto p-4 md:p-8">
        {server ? (
          // A new list (a refresh, or someone else's save) starts the choices again.
          <ReviewForm key={server.toolsHash} server={server} />
        ) : servers.status === "loading" ? (
          <Skeleton className="h-40 rounded-2xl" />
        ) : (
          <p className="text-sm text-muted-foreground">This MCP server doesn&apos;t exist, or you can&apos;t see it.</p>
        )}
      </div>
    </div>
  );
}

function ReviewForm({ server }: { server: McpServer }) {
  const canEdit = useCurrentUser().role !== "member";
  const [choices, setChoices] = useState(() => initialChoices(server.tools));
  const [saving, setSaving] = useState(false);
  const tools = reviewOrder(server.tools);
  const offered = Object.values(choices).filter((c) => c.enabled).length;

  async function save() {
    setSaving(true);
    const result = await actions.reviewMcpTools(server.id, server.toolsHash, Object.values(choices));
    setSaving(false);
    if (!result.ok) {
      toast.error(result.error);
      void actions.loadMcpServers(); // a 409 means the list changed: show the new one
      return;
    }
    toast.success(`${server.name}: ${offered === 1 ? "1 tool" : `${offered} tools`} offered to bots`);
  }

  return (
    <>
      <div>
        <h2 className="text-lg font-semibold">{server.name}</h2>
        <p className="text-sm break-all text-muted-foreground">{server.url}</p>
      </div>
      {server.toolsChanged > 0 && (
        <Alert>
          <AlertTitle>{server.toolsChanged === 1 ? "1 tool changed" : `${server.toolsChanged} tools changed`} on the server</AlertTitle>
          <AlertDescription>
            Changed and new tools aren&apos;t offered to bots until {canEdit ? "you approve them here" : "an owner or admin approves them"}. Read what they say now: a tool&apos;s description goes into every bot&apos;s instructions.
          </AlertDescription>
        </Alert>
      )}
      <p className="text-sm text-muted-foreground">
        Every tool starts as &ldquo;sends outside your org&rdquo;, so bots ask before using it. What a tool returns is outside text: after it, risky actions always wait for approval.
      </p>
      <ul className="flex flex-col gap-3">
        {tools.map((tool) => (
          <McpToolReviewItem
            key={tool.name}
            tool={tool}
            choice={choices[tool.serverName]}
            canEdit={canEdit}
            onChange={(choice: McpToolChoice) => setChoices((prev) => ({ ...prev, [choice.serverName]: choice }))}
          />
        ))}
      </ul>
      {canEdit ? (
        <div className="sticky bottom-0 flex items-center gap-3 border-t bg-background py-3">
          <p className="flex-1 text-sm text-muted-foreground">{offered === 1 ? "1 tool" : `${offered} tools`} will be offered to bots.</p>
          <Button onClick={() => void save()} disabled={saving}>{saving ? "Saving…" : server.toolsChanged > 0 ? "Approve and save" : "Save"}</Button>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Only owners and admins can change these.</p>
      )}
    </>
  );
}
