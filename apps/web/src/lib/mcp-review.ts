import type { McpTool, McpToolChoice, McpToolRisk } from "@/data/types";
import { stableJson } from "./text-diff";

/** The risks an admin may give an MCP tool, mildest first (never below read). */
export const MCP_TOOL_RISKS: McpToolRisk[] = ["read", "write-internal", "write-external", "external-send", "destructive"];

/** Below this, the admin is told what they're trusting: every MCP tool starts here. */
export const DEFAULT_MCP_RISK: McpToolRisk = "external-send";

export function isLowered(risk: McpToolRisk): boolean {
  return MCP_TOOL_RISKS.indexOf(risk) < MCP_TOOL_RISKS.indexOf(DEFAULT_MCP_RISK);
}

/** One argument of a tool, read from its JSON schema for people to look at. */
export interface ToolArgument {
  name: string;
  type: string;
  required: boolean;
  description: string | null;
}

export function toolArguments(schema: Record<string, unknown> | null | undefined): ToolArgument[] {
  const properties = schema?.properties;
  if (!properties || typeof properties !== "object") return [];
  const required = new Set(Array.isArray(schema?.required) ? schema.required.filter((r): r is string => typeof r === "string") : []);
  return Object.entries(properties as Record<string, unknown>).map(([name, raw]) => {
    const prop = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
    const type = Array.isArray(prop.type) ? prop.type.join(" | ") : typeof prop.type === "string" ? prop.type : "any";
    return { name, type, required: required.has(name), description: typeof prop.description === "string" ? prop.description : null };
  });
}

/** The review's starting choices: each tool as it is now (new tools start on, so approving offers them). */
export function initialChoices(tools: McpTool[]): Record<string, McpToolChoice> {
  return Object.fromEntries(
    tools
      .filter((t) => t.state !== "removed")
      .map((t) => [t.serverName, { serverName: t.serverName, enabled: t.state === "pending" ? true : t.enabled, risk: t.risk }]),
  );
}

/** The server says this tool only reads (MCP's `readOnlyHint`) and doesn't claim it destroys anything. */
export function saysItOnlyReads(tool: McpTool): boolean {
  return tool.annotations.readOnlyHint === true && tool.annotations.destructiveHint !== true;
}

/**
 * The server's own read-only claims, accepted in one go by a person who trusts the server: those
 * tools become "read" (they run without asking). Only tools the review shows and that aren't "read"
 * already. Returns the new choices and how many changed. Never applied without a click: the claims
 * are the server's, not checked (ADR 0012).
 */
export function withReadOnlyHints(tools: McpTool[], choices: Record<string, McpToolChoice>): { choices: Record<string, McpToolChoice>; changed: number } {
  let changed = 0;
  const next = { ...choices };
  for (const tool of tools) {
    const choice = next[tool.serverName];
    if (!choice || choice.risk === "read" || !saysItOnlyReads(tool)) continue;
    next[tool.serverName] = { ...choice, risk: "read" };
    changed += 1;
  }
  return { choices: next, changed };
}

/** Tools the review must look at, first: changed, then new, then removed, then the rest (server order kept). */
export function reviewOrder(tools: McpTool[]): McpTool[] {
  const rank: Record<McpTool["state"], number> = { changed: 0, pending: 1, removed: 2, approved: 3 };
  return tools.map((tool, index) => ({ tool, index })).sort((a, b) => rank[a.tool.state] - rank[b.tool.state] || a.index - b.index).map((x) => x.tool);
}

/** Tools bots are offered now: approved as they are, and left on. */
export function offeredTools(tools: McpTool[]): McpTool[] {
  return tools.filter((t) => t.state === "approved" && t.enabled);
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** "2 tools offered to bots" (or none yet): what a server gives bots right now. */
export function offeredLabel(tools: McpTool[]): string {
  const n = offeredTools(tools).length;
  return n === 0 ? "No tools offered to bots yet" : `${plural(n, "tool", "tools")} offered to bots`;
}

/**
 * The badge for tools waiting for the review, or null: "3 tools to review" before the first
 * review, then "1 tool changed", "2 new tools", "1 tool removed", or "1 changed, 2 new".
 */
export function waitingLabel(tools: McpTool[]): string | null {
  const count = (state: McpTool["state"]) => tools.filter((t) => t.state === state).length;
  const [changed, pending, removed, approved] = [count("changed"), count("pending"), count("removed"), count("approved")];
  if (changed + pending + removed === 0) return null;
  if (approved + changed + removed === 0) return `${plural(pending, "tool", "tools")} to review`;
  const kinds = [changed && "changed", pending && "new", removed && "removed"].filter(Boolean);
  if (kinds.length > 1) return [changed && `${changed} changed`, pending && `${pending} new`, removed && `${removed} removed`].filter(Boolean).join(", ");
  if (changed) return `${plural(changed, "tool", "tools")} changed`;
  if (pending) return `${plural(pending, "new tool", "new tools")}`;
  return `${plural(removed, "tool", "tools")} removed`;
}

/** For a changed tool: which parts of what an admin approved are different now. */
export function changedParts(tool: McpTool): ("title" | "description" | "arguments" | "output")[] {
  const before = tool.previous;
  if (!before) return [];
  const same = (a: unknown, b: unknown) => stableJson(a ?? null) === stableJson(b ?? null);
  const parts: ("title" | "description" | "arguments" | "output")[] = [];
  if ((before.title ?? "") !== (tool.title ?? "")) parts.push("title");
  if ((before.description ?? "") !== (tool.description ?? "")) parts.push("description");
  if (!same(before.inputSchema, tool.inputSchema)) parts.push("arguments");
  if (!same(before.outputSchema, tool.outputSchema)) parts.push("output");
  return parts;
}
