import type { McpTool, McpToolChoice, McpToolRisk } from "@/data/types";

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

/** Tools the review must look at, first: changed, then new, then removed, then the rest (server order kept). */
export function reviewOrder(tools: McpTool[]): McpTool[] {
  const rank: Record<McpTool["state"], number> = { changed: 0, pending: 1, removed: 2, approved: 3 };
  return tools.map((tool, index) => ({ tool, index })).sort((a, b) => rank[a.tool.state] - rank[b.tool.state] || a.index - b.index).map((x) => x.tool);
}
