import { describe, expect, it } from "vitest";
import type { McpTool } from "@/data/types";
import { initialChoices, isLowered, reviewOrder, toolArguments } from "./mcp-review";

const tool = (serverName: string, state: McpTool["state"], enabled = true): McpTool => ({
  name: `mcp-1.${serverName}`, serverName, title: null, description: null, inputSchema: { type: "object" }, annotations: {},
  state, enabled, risk: "external-send", previous: null,
});

describe("MCP tool review", () => {
  it("reads a tool's arguments from its schema", () => {
    const schema = {
      type: "object",
      properties: { query: { type: "string", description: "What to find" }, limit: { type: ["integer", "null"] }, raw: true },
      required: ["query"],
    };
    expect(toolArguments(schema)).toEqual([
      { name: "query", type: "string", required: true, description: "What to find" },
      { name: "limit", type: "integer | null", required: false, description: null },
      { name: "raw", type: "any", required: false, description: null },
    ]);
    expect(toolArguments({ type: "object" })).toEqual([]);
    expect(toolArguments(null)).toEqual([]);
  });

  it("starts new tools on, keeps the admin's choices, and leaves removed tools out", () => {
    const choices = initialChoices([tool("a", "approved", false), tool("b", "pending", false), tool("c", "removed")]);
    expect(choices).toEqual({
      a: { serverName: "a", enabled: false, risk: "external-send" },
      b: { serverName: "b", enabled: true, risk: "external-send" },
    });
  });

  it("puts what changed first", () => {
    const order = reviewOrder([tool("a", "approved"), tool("b", "removed"), tool("c", "pending"), tool("d", "changed")]);
    expect(order.map((t) => t.serverName)).toEqual(["d", "c", "b", "a"]);
  });

  it("knows a risk below sends-outside-your-org is a lowering", () => {
    expect(isLowered("read")).toBe(true);
    expect(isLowered("write-external")).toBe(true);
    expect(isLowered("external-send")).toBe(false);
    expect(isLowered("destructive")).toBe(false);
  });
});
