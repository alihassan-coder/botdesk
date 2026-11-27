import { describe, expect, it } from "vitest";
import { catalogueEntryFor, MCP_CATALOGUE, normalizeMcpUrl, signInLine } from "./mcp-catalogue";

describe("MCP_CATALOGUE", () => {
  it("lists only https servers, each once, with a description and docs", () => {
    const ids = MCP_CATALOGUE.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
    const urls = MCP_CATALOGUE.map((e) => normalizeMcpUrl(e.url));
    expect(new Set(urls).size).toBe(urls.length);
    for (const entry of MCP_CATALOGUE) {
      expect(new URL(entry.url).protocol, entry.id).toBe("https:");
      expect(new URL(entry.docsUrl).protocol, entry.id).toBe("https:");
      expect(entry.description, entry.id).toMatch(/\.$/);
    }
  });

  it("sends GitHub's token in Authorization, as a bearer token", () => {
    const github = MCP_CATALOGUE.find((e) => e.id === "github");
    expect(github?.signIn).toMatchObject({ kind: "key", header: "Authorization", valuePlaceholder: expect.stringMatching(/^Bearer /) });
  });
});

describe("normalizeMcpUrl", () => {
  it("lowercases the host, drops a trailing slash and the fragment, and keeps the path's case", () => {
    expect(normalizeMcpUrl(" https://MCP.Linear.app/mcp/ ")).toBe("https://mcp.linear.app/mcp");
    expect(normalizeMcpUrl("https://mcp.stripe.com/")).toBe("https://mcp.stripe.com");
    expect(normalizeMcpUrl("https://mcp.example.com/Path#top")).toBe("https://mcp.example.com/Path");
    expect(normalizeMcpUrl("https://mcp.example.com/mcp?team=1")).toBe("https://mcp.example.com/mcp?team=1");
  });

  it("still compares something that isn't a URL", () => {
    expect(normalizeMcpUrl("Not a URL/")).toBe("not a url");
  });
});

describe("catalogueEntryFor", () => {
  it("finds the catalogue server at an address written another way", () => {
    expect(catalogueEntryFor("https://API.githubcopilot.com/mcp")?.id).toBe("github");
    expect(catalogueEntryFor("https://mcp.hubspot.com")?.id).toBe("hubspot");
    expect(catalogueEntryFor("https://mcp.linear.app/sse")).toBeUndefined();
    expect(catalogueEntryFor("https://mcp.example.com/mcp")).toBeUndefined();
  });
});

describe("signInLine", () => {
  const entry = (id: string) => MCP_CATALOGUE.find((e) => e.id === id)!;

  it("says how each kind signs in", () => {
    expect(signInLine(entry("linear"))).toBe("Sign in with Linear");
    expect(signInLine(entry("atlassian"))).toBe("Sign in with Atlassian");
    expect(signInLine(entry("github"))).toBe("Needs a personal access token");
    expect(signInLine(entry("gmail"))).toBe("Needs an app you create in Google Cloud");
    expect(signInLine(entry("slack"))).toBe("Needs an app you create in Slack");
  });
});
