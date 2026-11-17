import { TriangleAlert } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import type { McpTool, McpToolChoice, McpToolRisk } from "@/data/types";
import { RISK } from "@/features/approvals/risk";
import { MCP_TOOL_RISKS, isLowered } from "@/lib/mcp-review";
import { McpToolArguments } from "./mcp-tool-arguments";

const STATE: Partial<Record<McpTool["state"], { label: string; variant: "default" | "destructive" | "outline" }>> = {
  changed: { label: "Changed", variant: "default" },
  pending: { label: "New", variant: "outline" },
  removed: { label: "Removed", variant: "destructive" },
};

/** One tool on the review screen: what it says it does, its arguments, and the admin's choices. */
export function McpToolReviewItem({
  tool, choice, canEdit, onChange,
}: { tool: McpTool; choice: McpToolChoice | undefined; canEdit: boolean; onChange: (choice: McpToolChoice) => void }) {
  const state = STATE[tool.state];
  const title = tool.title ?? tool.serverName;
  const id = `tool-${tool.name}`;
  const claims = Object.entries(tool.annotations).filter(([key, value]) => key.endsWith("Hint") && value === true).map(([key]) => key.replace(/Hint$/, ""));

  return (
    <li
      aria-label={title}
      data-state={tool.state}
      className="flex flex-col gap-3 rounded-2xl border bg-card p-4 data-[state=changed]:border-primary data-[state=pending]:border-dashed data-[state=removed]:opacity-70"
    >
      <div className="flex flex-wrap items-center gap-2">
        <p className="min-w-0 flex-1 font-medium break-words">
          {title} <code className="text-xs font-normal text-muted-foreground">{tool.serverName}</code>
        </p>
        {state && <Badge variant={state.variant}>{state.label}</Badge>}
      </div>

      {tool.state === "changed" && tool.previous ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl bg-muted/50 p-3">
            <p className="mb-1 text-xs font-medium text-muted-foreground">Before (approved)</p>
            <p className="text-sm whitespace-pre-wrap">{tool.previous.description || "No description."}</p>
            <div className="mt-2"><McpToolArguments schema={tool.previous.inputSchema} label="Arguments before" /></div>
          </div>
          <div className="rounded-xl border border-primary/40 p-3">
            <p className="mb-1 text-xs font-medium text-muted-foreground">Now</p>
            <p className="text-sm whitespace-pre-wrap">{tool.description || "No description."}</p>
            <div className="mt-2"><McpToolArguments schema={tool.inputSchema} label="Arguments now" /></div>
          </div>
        </div>
      ) : (
        <>
          <p className="text-sm whitespace-pre-wrap text-muted-foreground">{tool.description || "No description."}</p>
          <McpToolArguments schema={tool.inputSchema} label="Arguments" />
        </>
      )}
      {claims.length > 0 && <p className="text-xs text-muted-foreground">The server says it is: {claims.join(", ")} (not checked; it doesn&apos;t set the risk).</p>}

      {tool.state === "removed" ? (
        <p className="text-sm text-muted-foreground">The server no longer lists this tool. Bots can&apos;t use it; saving the review clears it.</p>
      ) : choice && (
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <label htmlFor={id} className="flex items-center gap-2 text-sm">
            <Checkbox id={id} checked={choice.enabled} disabled={!canEdit} onCheckedChange={(v) => onChange({ ...choice, enabled: v === true })} />
            Offer to bots
          </label>
          <label className="flex items-center gap-2 text-sm">
            Risk
            <NativeSelect size="sm" value={choice.risk} disabled={!canEdit} aria-label={`Risk of ${title}`}
              onChange={(e) => onChange({ ...choice, risk: e.target.value as McpToolRisk })}>
              {MCP_TOOL_RISKS.map((risk) => <NativeSelectOption key={risk} value={risk}>{RISK[risk].label}</NativeSelectOption>)}
            </NativeSelect>
          </label>
        </div>
      )}
      {choice && isLowered(choice.risk) && (
        <Alert>
          <TriangleAlert />
          <AlertDescription>
            Below &ldquo;sends outside your org&rdquo;, this tool may run without asking. The server still sees every argument, and if it can reach the internet that&apos;s still a way out. After any MCP result, actions above internal notes ask anyway. This change is recorded in the audit log.
          </AlertDescription>
        </Alert>
      )}
    </li>
  );
}
