import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { actions } from "@/data/store";
import { readOAuthReturn } from "@/lib/connections";
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
  afterEach(() => {
    leave.mockRestore();
    window.history.pushState({}, "", "/");
  });
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

  it("remembers the page Connect was pressed on, so signing in comes back there", async () => {
    api.routes["POST /api/v1/orgs/o1/connections/oauth/start"] = { status: 200, body: { authorizeUrl: "https://accounts.example/authorize" } };
    await signInOnApi();
    window.history.pushState({}, "", "/chat/t1?from=connect");

    await expect(actions.startOAuth("gmail", { kind: "member" }, "full")).resolves.toEqual({ ok: true });

    expect(leave).toHaveBeenCalledWith("https://accounts.example/authorize");
    expect(readOAuthReturn()).toBe("/chat/t1?from=connect");
  });

  it("remembers nothing when the start is refused", async () => {
    api.routes["POST /api/v1/orgs/o1/connections/oauth/start"] = { status: 400, body: { detail: "Gmail isn't set up on this server." } };
    await signInOnApi();
    window.history.pushState({}, "", "/chat/t1");

    await expect(actions.startOAuth("gmail", { kind: "member" })).resolves.toEqual({ ok: false, error: "Gmail isn't set up on this server." });

    expect(leave).not.toHaveBeenCalled();
    expect(readOAuthReturn()).toBe("/apps"); // nothing remembered: the default
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
  // The API's shape since slice 7.4: each tool carries its review state, and only approved, enabled ones are offered.
  const mcpTool = (serverName: string, title: string | null, state = "approved", enabled = true) => ({
    name: `mcp-1a2b3c4d.${serverName}`, serverName, title, description: `${serverName}.`, annotations: {}, inputSchema: { type: "object" },
    outputSchema: null, state, enabled, risk: "external-send", previous: null,
  });
  const tracker = {
    id: "m1", pluginId: "mcp-1a2b3c4d", name: "Tracker", url: "https://mcp.example.com/mcp", authKind: "header", authHeader: "X-API-Key",
    status: "active", statusReason: null, lastCheckedAt: "2026-11-17T08:00:00Z", createdAt: "2026-11-17T08:00:00Z", createdBy: "u1",
    tools: [mcpTool("search_issues", "Search issues"), mcpTool("create_issue", null)], toolsHash: "h1", toolsChanged: 0,
  };
  // What adding it returns: nothing approved yet (ADR 0012 §4).
  const justAdded = {
    ...tracker, tools: [mcpTool("search_issues", "Search issues", "pending", false), mcpTool("create_issue", null, "pending", false)],
    toolsChanged: 2, authorizeUrl: null,
  };
  beforeEach(() => {
    api.routes["GET /api/v1/orgs/o1/connectors"] = { status: 200, body: [] };
    api.routes["GET /api/v1/orgs/o1/connections"] = { status: 200, body: [] };
  });

  it("an owner adds a server with a header key; nothing is offered until its tools are reviewed, and the key isn't kept", async () => {
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = { status: 200, body: [] };
    api.routes["POST /api/v1/orgs/o1/mcp-servers"] = { status: 201, body: justAdded };
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

    // Step 2 of the dialog leads to Review tools.
    expect(await within(dialog).findByText("Tracker added")).toBeInTheDocument();
    expect(within(dialog).getByText(/2 tools to review/)).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Review tools" })).toHaveAttribute("href", "/apps/mcp/m1");
    await user.click(within(dialog).getByRole("button", { name: "Later" }));
    const row = await within(section).findByRole("listitem", { name: "Tracker" });
    expect(within(row).getByText(/No tools offered to bots yet/)).toBeInTheDocument();
    expect(within(row).getByText("2 tools to review")).toBeInTheDocument();
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
    api.routes["POST /api/v1/orgs/o1/mcp-servers/m1/refresh"] = { status: 200, body: { ...tracker, tools: tracker.tools.slice(0, 1), toolsHash: "h2" } };
    api.routes["DELETE /api/v1/orgs/o1/mcp-servers/m1"] = { status: 204 };
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    const row = await screen.findByRole("listitem", { name: "Tracker" });
    expect(within(row).getByText(/2 tools offered to bots$/)).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Refresh Tracker" }));
    expect(await within(row).findByText(/1 tool offered to bots$/)).toBeInTheDocument();

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
  it("a changed tool shows as a badge, and Review tools is the next step", async () => {
    const changed = { ...mcpTool("create_issue", null, "changed", true), previous: { title: null, description: "Old.", inputSchema: { type: "object" }, outputSchema: null } };
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = { status: 200, body: [{ ...tracker, tools: [tracker.tools[0], changed], toolsChanged: 1 }] };
    await signInOnApi();
    renderUI(<AppsScreen />);

    const row = await screen.findByRole("listitem", { name: "Tracker" });
    expect(within(row).getByText("1 tool changed")).toBeInTheDocument();
    expect(within(row).getByText(/1 tool offered to bots$/)).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Review tools" })).toHaveAttribute("href", "/apps/mcp/m1");
  });

  it("a sign-in that needs more access says why, and Reconnect signs in again", async () => {
    const oauth = { ...tracker, authKind: "oauth", authHeader: null, status: "needs_reconnect", statusReason: "Tracker needs more access than it was given (tracker.write)." };
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = { status: 200, body: [oauth] };
    api.routes["POST /api/v1/orgs/o1/mcp-servers/m1/sign-in"] = { status: 200, body: { authorizeUrl: "https://auth.example/authorize?x=1" } };
    const leave = vi.spyOn(browser, "leaveFor").mockImplementation(() => {});
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    const row = await screen.findByRole("listitem", { name: "Tracker" });
    expect(within(row).getByRole("status")).toHaveTextContent("needs more access than it was given (tracker.write)");
    await user.click(within(row).getByRole("button", { name: "Reconnect" }));
    await vi.waitFor(() => expect(leave).toHaveBeenCalledWith("https://auth.example/authorize?x=1"));
    leave.mockRestore();
  });

  it("an MCP sign-in in Your connections is named after its server and reconnects through it", async () => {
    const oauth = { ...tracker, authKind: "oauth", authHeader: null, status: "needs_reconnect" };
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = { status: 200, body: [oauth] };
    api.routes["GET /api/v1/orgs/o1/connections"] = {
      status: 200,
      body: [{ id: "c9", connectorId: "mcp-1a2b3c4d", ownerKind: "org", ownerUserId: null, ownerBotId: null, authType: "oauth2", accountLabel: "Tracker",
        scopes: [], status: "needs_reconnect", statusReason: "The MCP server stopped accepting this sign-in.", createdAt: "2026-11-17T08:00:00Z", lastUsedAt: null, createdBy: "u1" }],
    };
    api.routes["POST /api/v1/orgs/o1/mcp-servers/m1/sign-in"] = { status: 200, body: { authorizeUrl: "https://auth.example/authorize?y=2" } };
    const leave = vi.spyOn(browser, "leaveFor").mockImplementation(() => {});
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    const mine = await screen.findByRole("region", { name: "Your connections" });
    expect(await within(mine).findByText("Tracker (MCP)")).toBeInTheDocument();
    await user.click(within(mine).getByRole("button", { name: "Reconnect" }));
    await vi.waitFor(() => expect(leave).toHaveBeenCalledWith("https://auth.example/authorize?y=2"));
    expect(api.sent.some((r) => r.key === "POST /api/v1/orgs/o1/connections/oauth/start")).toBe(false);
    leave.mockRestore();
  });
});
