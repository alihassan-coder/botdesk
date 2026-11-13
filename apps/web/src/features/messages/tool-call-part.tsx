import { Ban, Check, TriangleAlert, Wrench } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import type { ToolCallPart as ToolCallPartData } from "@/data/types";
import { toolTitle } from "@/lib/approval-text";

const STATUS = {
  running: { icon: <Spinner className="size-3.5" />, verb: "Using", outcome: "" },
  succeeded: { icon: <Check className="size-3.5 text-success" />, verb: "Used", outcome: "done" },
  failed: { icon: <TriangleAlert className="size-3.5 text-destructive" />, verb: "Tried", outcome: "failed" },
  denied: { icon: <Ban className="size-3.5 text-muted-foreground" />, verb: "Didn't use", outcome: "not allowed" },
} satisfies Record<ToolCallPartData["status"], { icon: React.ReactNode; verb: string; outcome: string }>;

/** A compact line for a tool the bot used: "Used Send email · done", or why it didn't work. */
export function ToolCallPart({ part }: { part: ToolCallPartData }) {
  const { icon, verb, outcome } = STATUS[part.status];
  return (
    <div className="flex w-fit max-w-full flex-col gap-0.5 rounded-xl border px-3 py-1.5 text-xs text-muted-foreground" role="status">
      <span className="flex items-center gap-1.5">
        <Wrench className="size-3.5" aria-hidden />
        {verb} <span className="font-medium text-foreground">{toolTitle(part.tool)}</span>
        {outcome && <> · {outcome}</>}
        {icon}
      </span>
      {part.error && part.status !== "succeeded" && <span className="pl-5">{part.error}</span>}
    </div>
  );
}
