import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { browser } from "@/lib/navigate";
import { renderUI } from "@/test/render";
import { apiMe, apiOrg, signInOnApi, withFakeApi } from "@/test/fake-api";
import { AppsScreen } from "./apps-screen";

const server = (id: string, name: string, url: string, iconUrl?: string | null) => ({
  id, pluginId: `mcp-${id}`, name, url, authKind: "oauth", authHeader: null, status: "active", statusReason: null, lastCheckedAt: "2026-11-27T08:00:00Z",
  createdAt: "2026-11-27T08:00:00Z", createdBy: "u1", tools: [], toolsHash: "h", toolsChanged: 0, ...(iconUrl === undefined ? {} : { iconUrl }),
});
const ICON = "data:image/png;base64,iVBORw0KGgo=";

describe("Official MCP servers in the demo", () => {
  it("are shown with Connect off, and say how to connect them", () => {
    renderUI(<AppsScreen />);
    const official = screen.getByRole("region", { name: "Official MCP servers" });
    expect(within(official).getByText("Sign up to connect MCP servers.")).toBeInTheDocument();
    expect(within(official).getByRole("button", { name: "Connect Linear MCP server" })).toBeDisabled();
    // The demo's own custom server card is under Available; there's no second one here.
    expect(within(official).queryByRole("article", { name: "Custom MCP server" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect Custom MCP server" })).toBeEnabled();
  });
});

describe("Official MCP servers on the API", () => {
  const api = withFakeApi();
  let leave: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    leave = vi.spyOn(browser, "leaveFor").mockImplementation(() => {});
    api.routes["GET /api/v1/orgs/o1/connectors"] = { status: 200, body: [] };
    api.routes["GET /api/v1/orgs/o1/connections"] = { status: 200, body: [] };
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = { status: 200, body: [] };
  });
  afterEach(() => leave.mockRestore());

  const official = () => screen.findByRole("region", { name: "Official MCP servers" });
  const added = (name: string, url: string) => ({ ...server("m9", name, url), tools: [], toolsChanged: 0, authorizeUrl: null });

  it("lists each official server with how it signs in, then a custom one", async () => {
    await signInOnApi();
    renderUI(<AppsScreen />);

    const section = await official();
    expect(within(section).getByRole("article", { name: "Linear MCP server" })).toHaveTextContent("Sign in with Linear");
    expect(within(section).getByRole("article", { name: "GitHub MCP server" })).toHaveTextContent("Needs a personal access token");
    const gmail = within(section).getByRole("article", { name: "Gmail MCP server" });
    expect(within(gmail).getByText("by Google")).toBeInTheDocument();
    expect(within(gmail).getByText("Search and read email, and draft replies.")).toBeInTheDocument();
    expect(within(gmail).getByText("Needs an app you create in Google Cloud")).toBeInTheDocument();
    expect(within(section).getByRole("article", { name: "Custom MCP server" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Coming soon" })).not.toBeInTheDocument();
  });

  it("Connect on a one-click server fills in the dialog with sign-in on, and goes to sign in", async () => {
    api.routes["POST /api/v1/orgs/o1/mcp-servers"] = { status: 201, body: { ...added("Linear", "https://mcp.linear.app/mcp"), authorizeUrl: "https://linear.example/authorize" } };
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    await user.click(within(await official()).getByRole("button", { name: "Connect Linear MCP server" }));
    const dialog = screen.getByRole("dialog", { name: "Connect Linear" });
    expect(within(dialog).getByLabelText("Name")).toHaveValue("Linear");
    expect(within(dialog).getByLabelText("Server URL")).toHaveValue("https://mcp.linear.app/mcp");
    expect(within(dialog).getByRole("checkbox", { name: "Uses sign-in (OAuth)" })).toBeChecked();
    expect(within(dialog).getByText("OAuth client (optional)")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Add and sign in" }));

    await vi.waitFor(() => expect(leave).toHaveBeenCalledWith("https://linear.example/authorize"));
    expect(api.sent.find((r) => r.key === "POST /api/v1/orgs/o1/mcp-servers")?.body).toEqual({ name: "Linear", url: "https://mcp.linear.app/mcp", signIn: true });
  });

  it("Connect on GitHub asks for its token in Authorization, with where to get one", async () => {
    api.routes["POST /api/v1/orgs/o1/mcp-servers"] = { status: 201, body: added("GitHub", "https://api.githubcopilot.com/mcp/") };
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    await user.click(within(await official()).getByRole("button", { name: "Connect GitHub MCP server" }));
    const dialog = screen.getByRole("dialog", { name: "Connect GitHub" });
    const signIn = within(dialog).getByRole("checkbox", { name: "Uses sign-in (OAuth)" });
    expect(signIn).not.toBeChecked();
    expect(signIn).toBeDisabled(); // GitHub's server takes a token: its preset decides
    expect(within(dialog).getByLabelText("Header name")).toHaveValue("Authorization");
    expect(within(dialog).getByLabelText("Header value")).toHaveAttribute("placeholder", "ghp_…");
    expect(within(dialog).getByRole("link", { name: "GitHub's guide" })).toHaveAttribute("href", "https://github.com/github/github-mcp-server");
    expect(within(dialog).getByRole("button", { name: "Add server" })).toBeDisabled(); // the token is required
    await user.type(within(dialog).getByLabelText("Header value"), "ghp_made-up"); // pasted bare: "Bearer " is added
    await user.click(within(dialog).getByRole("button", { name: "Add server" }));

    expect(await within(dialog).findByText("GitHub added")).toBeInTheDocument();
    expect(api.sent.find((r) => r.key === "POST /api/v1/orgs/o1/mcp-servers")?.body).toEqual({
      name: "GitHub", url: "https://api.githubcopilot.com/mcp/", apiKeyHeader: "Authorization", apiKeyValue: "Bearer ghp_made-up",
    });
  });

  it("Connect on Gmail needs the app made in Google Cloud, and gives the redirect URI to paste there", async () => {
    // The API's own address, which can differ from the one this app calls it at (a proxy).
    const callback = "https://api.botdesk.example/api/v1/oauth/callback";
    api.routes["GET /api/v1/auth/options"] = { status: 200, body: { signUpMode: "open", oauthCallbackUrl: callback } };
    api.routes["POST /api/v1/orgs/o1/mcp-servers"] = { status: 201, body: { ...added("Gmail", "https://gmailmcp.googleapis.com/mcp/v1"), authorizeUrl: "https://accounts.example/o" } };
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    await user.click(within(await official()).getByRole("button", { name: "Connect Gmail MCP server" }));
    const dialog = screen.getByRole("dialog", { name: "Connect Gmail" });
    expect(within(dialog).getByRole("checkbox", { name: "Uses sign-in (OAuth)" })).toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: "Uses sign-in (OAuth)" })).toBeDisabled();
    expect(within(dialog).getByText("OAuth client")).toBeInTheDocument();
    expect(within(dialog).getByText(/create an OAuth client of type Web application/)).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Google's guide" })).toHaveAttribute("href", expect.stringContaining("developers.google.com"));
    await vi.waitFor(() => expect(within(dialog).getByLabelText("Redirect URI")).toHaveValue(callback));
    await user.click(within(dialog).getByRole("button", { name: "Copy redirect URI" }));
    expect(await navigator.clipboard.readText()).toBe(callback);
    expect(within(dialog).getByRole("button", { name: "Copied redirect URI" })).toBeInTheDocument();

    const submit = within(dialog).getByRole("button", { name: "Add and sign in" });
    expect(within(dialog).getByLabelText("Client ID")).toBeRequired();
    expect(submit).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Client ID"), "123.apps.example");
    expect(submit).toBeDisabled(); // and its secret
    await user.type(within(dialog).getByLabelText("Client secret"), "made-up-secret");
    await user.click(submit);

    await vi.waitFor(() => expect(leave).toHaveBeenCalledWith("https://accounts.example/o"));
    expect(api.sent.find((r) => r.key === "POST /api/v1/orgs/o1/mcp-servers")?.body).toEqual({
      name: "Gmail", url: "https://gmailmcp.googleapis.com/mcp/v1", signIn: true, oauthClientId: "123.apps.example", oauthClientSecret: "made-up-secret",
    });
  });

  it("Connect on the custom card opens the empty dialog", async () => {
    await signInOnApi();
    const { user } = renderUI(<AppsScreen />);

    await user.click(within(await official()).getByRole("button", { name: "Connect Custom MCP server" }));
    const dialog = screen.getByRole("dialog", { name: "Add MCP server" });
    expect(within(dialog).getByLabelText("Name")).toHaveValue("");
    expect(within(dialog).getByLabelText("Server URL")).toHaveValue("");
    expect(within(dialog).getByRole("checkbox", { name: "Uses sign-in (OAuth)" })).not.toBeChecked();
    expect(within(dialog).getByText("API key (optional)")).toBeInTheDocument();
  });

  it("an official server that's already added says so instead of Connect, at whatever address it was written", async () => {
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = { status: 200, body: [server("m1", "Our Linear", "https://MCP.linear.app/mcp/")] };
    await signInOnApi();
    renderUI(<AppsScreen />);

    const linear = within(await official()).getByRole("article", { name: "Linear MCP server" });
    expect(await within(linear).findByText("Added")).toBeInTheDocument();
    expect(within(linear).queryByRole("button")).not.toBeInTheDocument();
    expect(within(await official()).getByRole("button", { name: "Connect Notion MCP server" })).toBeEnabled();
  });

  it("members see the official servers without Connect", async () => {
    api.routes["POST /api/v1/auth/sign-in"] = { status: 200, body: { ...apiMe, organizations: [{ ...apiOrg, role: "member" }] } };
    api.routes["GET /api/v1/orgs/o1/members"] = { status: 200, body: [{ ...apiMe.user, role: "member" }] };
    await signInOnApi();
    renderUI(<AppsScreen />);

    const section = await official();
    expect(within(section).getByRole("article", { name: "Notion MCP server" })).toHaveTextContent("Sign in with Notion");
    expect(within(section).queryByRole("button")).not.toBeInTheDocument();
    expect(within(section).getByText(/Owners and admins connect these/)).toBeInTheDocument();
  });
});

describe("MCP server logos", () => {
  const api = withFakeApi();
  beforeEach(() => {
    api.routes["GET /api/v1/orgs/o1/connectors"] = { status: 200, body: [] };
    api.routes["GET /api/v1/orgs/o1/connections"] = { status: 200, body: [] };
  });
  const logo = (el: HTMLElement) => el.querySelector("[data-logo]");

  it("show the server's own icon, else the official server's mark, else its initial", async () => {
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = {
      status: 200,
      body: [
        server("m1", "Docs", "https://mcp.notion.com/mcp", ICON),
        server("m2", "Errors", "https://mcp.sentry.dev/mcp/", null),
        server("m3", "Tracker", "https://mcp.example.com/mcp"), // an older API: no iconUrl at all
      ],
    };
    await signInOnApi();
    renderUI(<AppsScreen />);

    const section = await screen.findByRole("region", { name: "MCP servers" });
    const docs = await within(section).findByRole("listitem", { name: "Docs" });
    expect(logo(docs)).toHaveAttribute("data-logo", "icon");
    expect(docs.querySelector("img")).toHaveAttribute("src", ICON);
    expect(logo(within(section).getByRole("listitem", { name: "Errors" }))).toHaveAttribute("data-logo", "brand");
    const tracker = logo(within(section).getByRole("listitem", { name: "Tracker" }));
    expect(tracker).toHaveAttribute("data-logo", "fallback");
    expect(tracker).toHaveTextContent("T");
  });

  it("show in Your connections for an MCP server's sign-in", async () => {
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = { status: 200, body: [server("m1", "Docs", "https://mcp.notion.com/mcp", ICON)] };
    api.routes["GET /api/v1/orgs/o1/connections"] = {
      status: 200,
      body: [{ id: "c9", connectorId: "mcp-m1", ownerKind: "org", ownerUserId: null, ownerBotId: null, authType: "oauth2", accountLabel: "Docs",
        scopes: [], status: "active", statusReason: null, createdAt: "2026-11-27T08:00:00Z", lastUsedAt: null, createdBy: "u1" }],
    };
    await signInOnApi();
    renderUI(<AppsScreen />);

    const mine = await screen.findByRole("region", { name: "Your connections" });
    await within(mine).findByText("Docs (MCP)");
    expect(logo(within(mine).getByRole("listitem"))).toHaveAttribute("data-logo", "icon");
  });
});
