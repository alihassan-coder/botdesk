import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { browser } from "@/lib/navigate";
import { renderUI } from "@/test/render";
import { apiMe, apiOrg, signInOnApi, withFakeApi } from "@/test/fake-api";
import { AppsScreen } from "./apps-screen";


describe("Connect apps in the demo", () => {
  it("shows the demo's connections and lets you connect Gmail", () => {
    renderUI(<AppsScreen />);
    expect(screen.getByRole("heading", { name: "Connected" })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "MCP servers" })).getByText(/Connect botdesk to its API to add MCP servers/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect Gmail" })).toBeEnabled();
    expect(screen.queryByRole("region", { name: "Your connections" })).not.toBeInTheDocument();
  });
});

describe("Connect apps on the API", () => {
  const api = withFakeApi();
  let leave: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    leave = vi.spyOn(browser, "leaveFor").mockImplementation(() => {});
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = { status: 200, body: [] };
  });
  afterEach(() => leave.mockRestore());
  const tools = [
    { name: "demo.send_email", title: "Send email", description: "Sends an email.", risk: "external-send" },
    { name: "demo.read_notes", title: "Read notes", description: "Reads notes.", risk: "read" },
  ];
  const demo = { id: "demo", name: "Demo", version: "0.1.0", description: "Tools to try approvals with.", authType: "api_key", setup: "ready", accessLevels: [], defaultAccess: null, tools };
  const notes = { id: "notes", name: "Notes", version: "1.0.0", description: "Built-in notes.", authType: null, setup: "ready", accessLevels: [], defaultAccess: null, tools: [] };
  const gmail = { id: "gmail", name: "Gmail", version: "0.1.0", description: "Your mail.", authType: "oauth2", setup: "ready", accessLevels: ["read", "full"], defaultAccess: "full", tools: [] };
  const zaraGmail = {
    id: "c1", connectorId: "gmail", ownerKind: "member", ownerUserId: "u1", ownerBotId: null, authType: "oauth2", accountLabel: "zara@example.com",
    scopes: [], status: "active", statusReason: null, createdAt: "2026-11-15T08:00:00Z", lastUsedAt: null, createdBy: "u1",
  };

  function serve(connectors: unknown[], connections: unknown[] = []) {
    api.routes["GET /api/v1/orgs/o1/connectors"] = { status: 200, body: connectors };
    api.routes["GET /api/v1/orgs/o1/connections"] = { status: 200, body: connections };
  }

  it("lists the server's connectors with their state, and each tool's risk", async () => {
    serve([notes, demo, gmail], [zaraGmail]);
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    const apps = await screen.findByRole("region", { name: "Apps" });
    expect(within(within(apps).getByRole("article", { name: "Notes" })).getByText("Built in")).toBeInTheDocument();
    expect(within(within(apps).getByRole("article", { name: "Gmail" })).getByText("Connected")).toBeInTheDocument();
    const demoCard = within(apps).getByRole("article", { name: "Demo" });
    await user.click(within(demoCard).getByRole("button", { name: /What bots can do \(2\)/ }));
    expect(within(demoCard).getByText("Sends outside your org")).toBeInTheDocument();
    // The catalogue keeps only what the server has no plugin for.
    const soon = screen.getByRole("region", { name: "Coming soon" });
    expect(within(soon).queryByText("Gmail")).not.toBeInTheDocument();
    expect(within(soon).getByText("Slack")).toBeInTheDocument();
  });

  it("Connect signs in with the provider: owner and access level go to the API, then the tab leaves for its page", async () => {
    serve([gmail]);
    api.routes["POST /api/v1/orgs/o1/connections/oauth/start"] = { status: 200, body: { authorizeUrl: "https://accounts.example/authorize?x=1" } };
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    // Wait for the server's card: until then the catalogue's own (disabled) Gmail card is there.
    await user.click(within(await screen.findByRole("article", { name: "Gmail" })).getByRole("button", { name: "Connect Gmail" }));
    expect(screen.getByRole("radio", { name: /Read, organise, draft and send/ })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: /Read only/ }));
    await user.click(screen.getByRole("radio", { name: /The organization/ }));
    await user.click(screen.getByRole("button", { name: "Continue to Gmail" }));

    await vi.waitFor(() => expect(leave).toHaveBeenCalledWith("https://accounts.example/authorize?x=1"));
    expect(api.sent.find((r) => r.key === "POST /api/v1/orgs/o1/connections/oauth/start")?.body).toEqual({ connectorId: "gmail", ownerKind: "org", access: "read" });
  });

  it("says when an app isn't set up on this server, with Connect off and a link to the guide", async () => {
    serve([{ ...gmail, setup: "not-configured" }]);
    await signInOnApi();
    renderUI(<AppsScreen />);

    const card = await screen.findByRole("article", { name: "Gmail" });
    expect(within(card).getByText("Not set up")).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Connect Gmail" })).toBeDisabled();
    expect(within(card).getByRole("link", { name: "How to set it up" })).toHaveAttribute("href", expect.stringContaining("docs/self-hosting/google-oauth.md"));
  });

  it("the Demo's key dialog warns the key goes to a public echo service, and connects with it", async () => {
    serve([demo]);
    api.routes["POST /api/v1/orgs/o1/connections"] = { status: 201, body: { ...zaraGmail, id: "c2", connectorId: "demo", authType: "api_key", accountLabel: "Try" } };
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    await user.click(await screen.findByRole("button", { name: "Connect Demo" }));
    expect(screen.getByText(/public echo service/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Account name"), "Try");
    await user.type(screen.getByLabelText("API key"), "made-up-key");
    await user.click(screen.getByRole("button", { name: "Connect" }));

    expect(await screen.findByText("Try", { exact: false, selector: "span" })).toBeInTheDocument();
    expect(api.sent.at(-1)).toEqual({ key: "POST /api/v1/orgs/o1/connections", body: { connectorId: "demo", ownerKind: "member", accountLabel: "Try", apiKey: "made-up-key" } });
  });

  it("lists your connections, offers Reconnect when one broke, and disconnects after a confirm", async () => {
    const broken = { ...zaraGmail, id: "c3", status: "needs_reconnect", statusReason: "Google refused the saved sign-in." };
    serve([gmail], [zaraGmail, broken, { ...zaraGmail, id: "old", status: "revoked", accountLabel: "gone@example.com" }]);
    api.routes["DELETE /api/v1/orgs/o1/connections/c1"] = { status: 204 };
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    const mine = await screen.findByRole("region", { name: "Your connections" });
    expect(within(mine).queryByText(/gone@example.com/)).not.toBeInTheDocument();
    expect(within(mine).getByText(/Google refused the saved sign-in/)).toBeInTheDocument();
    expect(within(mine).getByRole("button", { name: "Reconnect" })).toBeInTheDocument();

    await user.click(within(mine).getAllByRole("button", { name: "Disconnect" })[0]);
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Disconnect" }));
    await vi.waitFor(() => expect(api.sent.some((r) => r.key === "DELETE /api/v1/orgs/o1/connections/c1")).toBe(true));
    await vi.waitFor(() => expect(within(mine).getAllByRole("listitem")).toHaveLength(1));
  });

  it("says so, with Try again, when the apps can't be loaded", async () => {
    api.routes["GET /api/v1/orgs/o1/connectors"] = { status: 500, body: { detail: "Oops" } };
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    expect(await screen.findByText("Couldn't load the apps.")).toBeInTheDocument();
    serve([demo]);
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("article", { name: "Demo" })).toBeInTheDocument();
  });
});

describe("MCP servers on Connect apps", () => {
  const api = withFakeApi();
  const tracker = {
    id: "m1", pluginId: "mcp-1a2b3c4d", name: "Tracker", url: "https://mcp.example.com/mcp", authKind: "header", authHeader: "X-API-Key",
    status: "active", statusReason: null, lastCheckedAt: "2026-11-17T08:00:00Z", createdAt: "2026-11-17T08:00:00Z", createdBy: "u1",
    tools: [
      { name: "mcp-1a2b3c4d.search_issues", serverName: "search_issues", title: "Search issues", description: "Finds issues.", annotations: {} },
      { name: "mcp-1a2b3c4d.create_issue", serverName: "create_issue", title: null, description: "Creates one.", annotations: {} },
    ],
  };
  beforeEach(() => {
    api.routes["GET /api/v1/orgs/o1/connectors"] = { status: 200, body: [] };
    api.routes["GET /api/v1/orgs/o1/connections"] = { status: 200, body: [] };
  });

  it("an owner adds a server with a header key; it's listed with its tool count, and the key isn't kept", async () => {
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = { status: 200, body: [] };
    api.routes["POST /api/v1/orgs/o1/mcp-servers"] = { status: 201, body: tracker };
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    const section = await screen.findByRole("region", { name: "MCP servers" });
    expect(await within(section).findByText(/No MCP servers yet. Add one/)).toBeInTheDocument();
    await user.click(within(section).getByRole("button", { name: "Add server" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Name"), "Tracker");
    await user.type(within(dialog).getByLabelText("Server URL"), "https://mcp.example.com/mcp");
    await user.type(within(dialog).getByLabelText("Header name"), "X-API-Key");
    expect(within(dialog).getByRole("button", { name: "Add server" })).toBeDisabled(); // a header needs its key
    await user.type(within(dialog).getByLabelText("Header value"), "sk-secret");
    await user.click(within(dialog).getByRole("button", { name: "Add server" }));

    const row = await within(section).findByRole("listitem", { name: "Tracker" });
    expect(within(row).getByText(/2 tools/)).toBeInTheDocument();
    expect(api.sent.find((r) => r.key === "POST /api/v1/orgs/o1/mcp-servers")?.body).toEqual({
      name: "Tracker", url: "https://mcp.example.com/mcp", apiKeyHeader: "X-API-Key", apiKeyValue: "sk-secret",
    });
    expect(screen.queryByText("sk-secret")).not.toBeInTheDocument();
  });

  it("shows the API's refusal in the dialog (a private address, say)", async () => {
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = { status: 200, body: [] };
    api.routes["POST /api/v1/orgs/o1/mcp-servers"] = { status: 400, body: { detail: "That address is on a private network." } };
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    await user.click(await screen.findByRole("button", { name: "Add server" }));
    await user.type(screen.getByLabelText("Name"), "Local");
    await user.type(screen.getByLabelText("Server URL"), "https://127.0.0.1/mcp");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Add server" }));

    expect(await screen.findByText("That address is on a private network.")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument(); // stays open to fix the address
  });

  it("an owner refreshes and removes a server", async () => {
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = { status: 200, body: [tracker] };
    api.routes["POST /api/v1/orgs/o1/mcp-servers/m1/refresh"] = { status: 200, body: { ...tracker, tools: tracker.tools.slice(0, 1) } };
    api.routes["DELETE /api/v1/orgs/o1/mcp-servers/m1"] = { status: 204 };
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    const row = await screen.findByRole("listitem", { name: "Tracker" });
    await user.click(within(row).getByRole("button", { name: "Refresh Tracker" }));
    expect(await within(row).findByText(/1 tool$/)).toBeInTheDocument();

    await user.click(within(row).getByRole("button", { name: "Remove" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Remove" }));
    await vi.waitFor(() => expect(screen.queryByRole("listitem", { name: "Tracker" })).not.toBeInTheDocument());
    expect(api.sent.some((r) => r.key === "DELETE /api/v1/orgs/o1/mcp-servers/m1")).toBe(true);
  });

  it("members see the servers but can't add, refresh or remove them", async () => {
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = { status: 200, body: [tracker] };
    api.routes["POST /api/v1/auth/sign-in"] = { status: 200, body: { ...apiMe, organizations: [{ ...apiOrg, role: "member" }] } };
    api.routes["GET /api/v1/orgs/o1/members"] = { status: 200, body: [{ ...apiMe.user, role: "member" }] };
    await signInOnApi();
    renderUI(<AppsScreen />);

    const row = await screen.findByRole("listitem", { name: "Tracker" });
    expect(within(row).queryByRole("button", { name: /Refresh/ })).not.toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add server" })).not.toBeInTheDocument();
  });
});
