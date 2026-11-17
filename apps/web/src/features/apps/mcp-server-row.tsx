import { useState } from "react";
import Link from "next/link";
import { ListChecks, LogIn, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { actions } from "@/data/store";
import type { McpServer } from "@/data/types";
import { ToolList } from "./tool-list";

const STATUS: Record<McpServer["status"], { label: string; problem: boolean }> = {
  active: { label: "MCP", problem: false },
  unreachable: { label: "Unreachable", problem: true },
  needs_sign_in: { label: "Not signed in", problem: true },
  needs_reconnect: { label: "Needs reconnecting", problem: true },
};

/** One MCP server on Connect apps: its state, "Tools changed", and (owners and admins) what to do about it. */
export function McpServerRow({ server, canManage }: { server: McpServer; canManage: boolean }) {
  const [busy, setBusy] = useState<"refresh" | "sign-in" | null>(null);
  const status = STATUS[server.status];
  const needsSignIn = server.status === "needs_sign_in" || server.status === "needs_reconnect";
  const offered = server.tools.filter((t) => t.state === "approved" && t.enabled);

  async function refresh() {
    setBusy("refresh");
    const result = await actions.refreshMcpServer(server.id);
    setBusy(null);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`${server.name}'s tools are up to date`);
  }

  async function signIn() {
    setBusy("sign-in");
    const result = await actions.signInMcpServer(server.id); // leaves for the sign-in page
    setBusy(null);
    if (!result.ok) toast.error(result.error);
  }

  return (
    <li className="flex flex-col gap-3 rounded-2xl border bg-card p-4" aria-label={server.name}>
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-medium">{server.name}</p>
          <p className="truncate text-sm text-muted-foreground">
            {server.url} · {offered.length === 1 ? "1 tool on" : `${offered.length} tools on`}
            {server.status === "unreachable" && server.statusReason ? ` · ${server.statusReason}` : ""}
          </p>
        </div>
        {server.toolsChanged > 0 && (
          <Badge variant="outline">{server.toolsChanged === 1 ? "1 tool changed" : `${server.toolsChanged} tools changed`}</Badge>
        )}
        <Badge variant={status.problem ? "destructive" : "secondary"}>{status.label}</Badge>
      </div>
      {canManage && (
        <div className="flex flex-wrap items-center gap-1">
          {needsSignIn && (
            <Button size="sm" onClick={() => void signIn()} disabled={busy !== null}>
              <LogIn /> {server.status === "needs_reconnect" ? "Reconnect" : "Sign in"}
            </Button>
          )}
          <Button size="sm" variant={server.toolsChanged > 0 ? "default" : "ghost"} asChild>
            <Link href={`/apps/mcp/${server.id}`}><ListChecks /> Review tools</Link>
          </Button>
          <Button size="sm" variant="ghost" onClick={() => void refresh()} disabled={busy !== null} aria-label={`Refresh ${server.name}`}>
            <RefreshCw className={busy === "refresh" ? "animate-spin" : undefined} /> Refresh
          </Button>
          <RemoveButton server={server} />
        </div>
      )}
      {offered.length > 0 && <ToolList tools={offered.map((t) => ({ name: t.name, label: t.title ?? t.serverName, risk: t.risk }))} />}
    </li>
  );
}

function RemoveButton({ server }: { server: McpServer }) {
  const remove = async () => {
    const result = await actions.removeMcpServer(server.id);
    if (!result.ok) return void toast.error(result.error);
    toast.success(`Removed ${server.name}`);
  };

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="sm">Remove</Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove {server.name}?</AlertDialogTitle>
          <AlertDialogDescription>Every bot loses its tools straight away, and BotDesk forgets its key or sign-in. You can add it again later.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it</AlertDialogCancel>
          <AlertDialogAction variant="destructive" onClick={remove}>Remove</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
