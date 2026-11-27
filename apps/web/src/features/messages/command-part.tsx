import { Ban, Check, ChevronRight, CircleHelp, SquareTerminal, TriangleAlert } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Spinner } from "@/components/ui/spinner";
import type { ToolCallPart } from "@/data/types";
import { commandResult, formatSeconds, lineCount } from "@/lib/computer";
import { pluralize } from "@/lib/format";
import { cn } from "@/lib/utils";

const OUTCOME = {
  running: { icon: <Spinner className="size-3.5 motion-reduce:animate-none" />, text: "running" },
  succeeded: { icon: <Check className="size-3.5 text-success" />, text: "" },
  failed: { icon: <TriangleAlert className="size-3.5 text-destructive" />, text: "failed" },
  denied: { icon: <Ban className="size-3.5 text-muted-foreground" />, text: "not allowed" },
  // Cut off mid-way: it may have run (ADR 0020 §4), so a person checks.
  unknown: { icon: <CircleHelp className="size-3.5 text-destructive" />, text: "may have run" },
} satisfies Record<ToolCallPart["status"], { icon: React.ReactNode; text: string }>;

/**
 * A command the bot ran on its cloud computer (`computer.run`, or the read-only `computer.inspect`):
 * the command in a mono line, then its exit code (non-zero stands out), how long it took, and the
 * output in a block that opens on its own when the command failed.
 */
export function CommandPart({ part, command }: { part: ToolCallPart; command: string }) {
  const result = commandResult(part.result);
  const { icon, text } = OUTCOME[part.status];
  const failed = result !== undefined && result.exitCode !== 0;
  const cwd = result?.cwd ?? (typeof part.args?.cwd === "string" ? part.args.cwd : undefined);
  const lines = result ? lineCount(result.output) : 0;

  return (
    <div role="group" aria-label={part.tool === "computer.inspect" ? "Read-only command" : "Command"}
      className="flex w-full max-w-[560px] flex-col gap-1.5 rounded-xl border px-3 py-2 text-xs text-muted-foreground">
      <p className="flex flex-wrap items-center gap-1.5">
        <SquareTerminal className="size-3.5" aria-hidden />
        <span className="font-medium text-foreground">{part.tool === "computer.inspect" ? "Read-only command" : "Command"}</span>
        {text && <>· {text}</>}
        {result && (
          <span className={cn("rounded-md px-1.5 py-px font-mono tabular-nums", failed ? "bg-destructive/10 font-medium text-destructive" : "bg-muted")}>
            exit {result.exitCode}
          </span>
        )}
        {result?.seconds !== undefined && <span className="tabular-nums">{formatSeconds(result.seconds)}</span>}
        {icon}
      </p>
      <pre className="overflow-x-auto rounded-lg bg-muted/60 px-2.5 py-1.5 font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-all text-foreground">
        <span aria-hidden className="text-muted-foreground select-none">$ </span>{command}
      </pre>
      {cwd && <p>in <span className="font-mono">{cwd}</span></p>}
      {part.error && part.status !== "succeeded" && <p className="text-pretty">{part.error}</p>}
      {result && (lines === 0 ? <p>No output</p> : (
        <Collapsible defaultOpen={failed} className="group/output">
          <CollapsibleTrigger className="flex items-center gap-1 rounded-md outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
            <ChevronRight className="size-3.5 transition-transform motion-reduce:transition-none group-data-[state=open]/output:rotate-90" aria-hidden />
            Output · {pluralize(lines, "line")}
          </CollapsibleTrigger>
          <CollapsibleContent>
            {result.cut && <p className="mt-1.5">Long output: only its first and last 8 KB were kept.</p>}
            <pre tabIndex={0} role="region" aria-label="Output"
              className="mt-1.5 max-h-72 overflow-auto rounded-lg bg-muted/60 p-2.5 font-mono text-[11px] leading-relaxed whitespace-pre text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring">
              {result.output}
            </pre>
          </CollapsibleContent>
        </Collapsible>
      ))}
    </div>
  );
}
