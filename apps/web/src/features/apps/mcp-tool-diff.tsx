import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { McpTool } from "@/data/types";
import { changedParts } from "@/lib/mcp-review";
import { lineDiff, stableJson, wordDiff, type DiffPart } from "@/lib/text-diff";
import { McpToolArguments } from "./mcp-tool-arguments";

const PART_LABEL = { title: "Name", description: "Description", arguments: "Arguments", output: "What it returns" } as const;

/**
 * A changed MCP tool: what an admin approved against what the server says now (the drift diff,
 * ADR 0012 §4). Words taken out are struck through, words put in are marked; the schemas are
 * compared line by line as JSON, since a change deep inside one is still a change.
 */
export function McpToolDiff({ tool }: { tool: McpTool }) {
  const before = tool.previous;
  if (!before) return null;
  const parts = changedParts(tool);

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">
        Changed since it was approved: {parts.length > 0 ? parts.map((p) => PART_LABEL[p]).join(", ") : "nothing visible (only how it's written)"}.
      </p>
      {parts.includes("title") && (
        <DiffBlock label="Name">
          <Inline parts={wordDiff(before.title ?? "", tool.title ?? "")} />
        </DiffBlock>
      )}
      <DiffBlock label="Description">
        {parts.includes("description") ? <Inline parts={wordDiff(before.description ?? "", tool.description ?? "")} /> : <span>{tool.description || "No description."}</span>}
      </DiffBlock>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl bg-muted/50 p-3"><McpToolArguments schema={before.inputSchema} label="Arguments before" /></div>
        <div className="rounded-xl border border-primary/40 p-3"><McpToolArguments schema={tool.inputSchema} label="Arguments now" /></div>
      </div>
      {(parts.includes("arguments") || parts.includes("output")) && (
        <Collapsible className="group/schema">
          <CollapsibleTrigger className="tap-target flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground">
            <ChevronRight className="size-3.5 transition-transform group-data-[state=open]/schema:rotate-90" />
            Schema changes, line by line
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 flex flex-col gap-2">
            {parts.includes("arguments") && <Lines label="Arguments (JSON schema)" parts={lineDiff(stableJson(before.inputSchema), stableJson(tool.inputSchema))} />}
            {parts.includes("output") && <Lines label="What it returns (JSON schema)" parts={lineDiff(stableJson(before.outputSchema), stableJson(tool.outputSchema))} />}
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}

function DiffBlock({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-muted-foreground">{label}</p>
      <p className="text-sm whitespace-pre-wrap break-words">{children}</p>
    </div>
  );
}

/** Prose with what went struck through and what came in marked, readable without colour too. */
function Inline({ parts }: { parts: DiffPart[] }) {
  return parts.map((part, i) =>
    part.kind === "same" ? <span key={i}>{part.text}</span>
    : part.kind === "removed" ? <del key={i} className="rounded-sm bg-destructive/15 text-destructive line-through decoration-destructive/70"><span className="sr-only">removed: </span>{part.text}</del>
    : <ins key={i} className="rounded-sm bg-primary/15 font-medium no-underline"><span className="sr-only">added: </span>{part.text}</ins>,
  );
}

/** A schema's JSON, line by line, with − and + in the margin. */
function Lines({ label, parts }: { label: string; parts: DiffPart[] }) {
  return (
    <figure className="min-w-0">
      <figcaption className="mb-1 text-xs font-medium text-muted-foreground">{label}</figcaption>
      <pre className="max-h-80 overflow-auto rounded-xl border bg-muted/30 p-2 text-xs leading-5">
        {parts.flatMap((part, i) =>
          part.text.split("\n").map((line, j) => (
            <div
              key={`${i}-${j}`}
              data-kind={part.kind}
              className="whitespace-pre data-[kind=added]:bg-primary/15 data-[kind=removed]:bg-destructive/15 data-[kind=removed]:text-destructive"
            >
              {part.kind === "added" ? "+ " : part.kind === "removed" ? "− " : "  "}
              {line}
            </div>
          )),
        )}
      </pre>
    </figure>
  );
}
