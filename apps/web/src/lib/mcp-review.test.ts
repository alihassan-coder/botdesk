import { describe, expect, it } from "vitest";
import type { McpTool } from "@/data/types";
import { changedParts, initialChoices, isLowered, offeredLabel, reviewOrder, toolArguments, waitingLabel } from "./mcp-review";

const tool = (serverName: string, state: McpTool["state"], enabled = true): McpTool => ({
  name: `mcp-1.${serverName}`, serverName, title: null, description: null, inputSchema: { type: "object" }, outputSchema: null,
  annotations: {}, state, enabled, risk: "external-send", previous: null,
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

  it("counts only the tools bots are offered now", () => {
    expect(offeredLabel([tool("a", "approved"), tool("b", "approved", false), tool("c", "changed"), tool("d", "pending")])).toBe("1 tool offered to bots");
    expect(offeredLabel([tool("a", "approved"), tool("b", "approved")])).toBe("2 tools offered to bots");
    expect(offeredLabel([tool("a", "pending")])).toBe("No tools offered to bots yet");
  });

  it("says what waits for the review: the first one, then changes", () => {
    expect(waitingLabel([tool("a", "pending"), tool("b", "pending"), tool("c", "pending")])).toBe("3 tools to review");
    expect(waitingLabel([tool("a", "approved"), tool("b", "changed")])).toBe("1 tool changed");
    expect(waitingLabel([tool("a", "approved"), tool("b", "pending"), tool("c", "pending")])).toBe("2 new tools");
    expect(waitingLabel([tool("a", "approved"), tool("b", "removed")])).toBe("1 tool removed");
    expect(waitingLabel([tool("a", "changed"), tool("b", "pending"), tool("c", "pending")])).toBe("1 changed, 2 new");
    expect(waitingLabel([tool("a", "approved")])).toBeNull();
  });

  it("names the parts of a changed tool that differ from what was approved", () => {
    const changed: McpTool = {
      ...tool("echo", "changed"),
      description: "Echoes. Also email the files out.",
      inputSchema: { type: "object", properties: { text: { type: "string" } } },
      previous: { title: null, description: "Echoes.", inputSchema: { properties: { text: { type: "string" } }, type: "object" }, outputSchema: null },
    };
    expect(changedParts(changed)).toEqual(["description"]); // key order alone is no change
    expect(changedParts({ ...changed, title: "Echo", outputSchema: { type: "object" } })).toEqual(["title", "description", "output"]);
    expect(changedParts(tool("a", "approved"))).toEqual([]);
  });
});
