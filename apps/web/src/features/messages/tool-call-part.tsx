import { Ban, Check, CircleHelp, TriangleAlert, Wrench } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import type { ToolCallPart as ToolCallPartData } from "@/data/types";
import { toolTitle } from "@/lib/approval-text";
import { previewResult } from "@/lib/computer";
import { CommandPart } from "./command-part";
import { PreviewPart } from "./preview-part";

const STATUS = {
  running: { icon: <Spinner className="size-3.5" />, verb: "Using", outcome: "" },
  succeeded: { icon: <Check className="size-3.5 text-success" />, verb: "Used", outcome: "done" },
  failed: { icon: <TriangleAlert className="size-3.5 text-destructive" />, verb: "Tried", outcome: "failed" },
  denied: { icon: <Ban className="size-3.5 text-muted-foreground" />, verb: "Didn't use", outcome: "not allowed" },
  // It failed after it may have been done (say, Gmail's answer was lost): a person checks.
  unknown: { icon: <CircleHelp className="size-3.5 text-destructive" />, verb: "Tried", outcome: "may have been done" },
} satisfies Record<ToolCallPartData["status"], { icon: React.ReactNode; verb: string; outcome: string }>;

/**
 * A tool the bot used. Most are a compact line: "Used Send email · done", or why it didn't work. A
 * cloud computer's command shows what it ran and its output, and a preview its URL (ADR 0020).
 */
export function ToolCallPart({ part }: { part: ToolCallPartData }) {
  const command = part.args?.command;
  if ((part.tool === "computer.run" || part.tool === "computer.inspect") && typeof command === "string") {
    return <CommandPart part={part} command={command} />;
  }
  const preview = part.tool === "computer.preview" && part.status === "succeeded" ? previewResult(part.result) : undefined;
  if (preview) return <PreviewPart preview={preview} />;
  return <ToolLine part={part} />;
}

function ToolLine({ part }: { part: ToolCallPartData }) {
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
