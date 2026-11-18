import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { apiMe, apiOrg, signInOnApi, withFakeApi } from "@/test/fake-api";
import { BotTools } from "./bot-tools";

describe("A bot's Tools tab in the demo", () => {
  it("shows the demo's plugins, and a switch turns one on", async () => {
    const bot = getStoreSnapshot().bots[0];
    const { user } = renderUI(<BotTools bot={bot} />);

    const demo = await screen.findByRole("switch", { name: "Use Demo" });
    expect(demo).toBeChecked();
    const gmail = screen.getByRole("switch", { name: "Use Gmail" });
    expect(gmail).not.toBeChecked();
    await user.click(gmail);
    expect(gmail).toBeChecked();
    expect(screen.getByRole("option", { name: "ali@acme.dev (yours)" })).toBeInTheDocument();
  });
});

describe("A bot's Tools tab on the API", () => {
  const api = withFakeApi();
  const plugin = (patch: object) => ({
    pluginId: "demo", name: "Demo", description: "Tools to try approvals with.", authType: null, enabled: true, connectionId: null,
    tools: [{ name: "demo.send_email", title: "Send email", description: "Sends an email.", risk: "external-send" }],
    ...patch,
  });
  const gmail = plugin({ pluginId: "gmail", name: "Gmail", description: "Your mail.", authType: "oauth2", enabled: false, tools: [] });
  const account = (patch: object) => ({
    id: "c1", connectorId: "gmail", ownerKind: "member", ownerUserId: "u1", ownerBotId: null, authType: "oauth2", accountLabel: "zara@example.com",
    scopes: [], status: "active", statusReason: null, createdAt: "2026-11-15T08:00:00Z", lastUsedAt: null, createdBy: "u1", ...patch,
  });

  async function open() {
    await signInOnApi();
    const bot = getStoreSnapshot().bots.find((b) => b.id === "b1")!;
    return renderUI(<BotTools bot={bot} />);
  }

  it("lists the bot's plugins and the accounts it may use, never another member's", async () => {
    api.routes["GET /api/v1/orgs/o1/bots/b1/tools"] = { status: 200, body: { plugins: [plugin({}), gmail] } };
    api.routes["GET /api/v1/orgs/o1/connections"] = {
      status: 200,
      body: [account({}), account({ id: "c2", ownerUserId: "u2", accountLabel: "sara@example.com" }), account({ id: "c3", ownerKind: "org", ownerUserId: null, accountLabel: "team@example.com" })],
    };
    await open();

    expect(await screen.findByRole("switch", { name: "Use Demo" })).toBeChecked();
    const card = screen.getByRole("article", { name: "Gmail" });
    const select = within(card).getByLabelText("Account");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "No account", "zara@example.com (yours)", "team@example.com (organization)",
    ]);
  });

  it("turning a plugin on, or picking its account, saves only that plugin", async () => {
    api.routes["GET /api/v1/orgs/o1/bots/b1/tools"] = { status: 200, body: { plugins: [plugin({}), gmail] } };
    api.routes["GET /api/v1/orgs/o1/connections"] = { status: 200, body: [account({})] };
    api.routes["PUT /api/v1/orgs/o1/bots/b1/tools"] = { status: 200, body: { plugins: [plugin({}), { ...gmail, enabled: true }] } };
    const { user } = await open();

    await user.click(await screen.findByRole("switch", { name: "Use Gmail" }));
    await vi.waitFor(() => expect(screen.getByRole("switch", { name: "Use Gmail" })).toBeChecked());
    expect(api.sent.at(-1)).toEqual({
      key: "PUT /api/v1/orgs/o1/bots/b1/tools",
      body: { plugins: [{ pluginId: "gmail", enabled: true, connectionId: null }] },
    });

    api.routes["PUT /api/v1/orgs/o1/bots/b1/tools"] = { status: 200, body: { plugins: [plugin({}), { ...gmail, enabled: true, connectionId: "c1" }] } };
    await user.selectOptions(screen.getByLabelText("Account"), "c1");
    await vi.waitFor(() => expect(api.sent.at(-1)?.body).toEqual({ plugins: [{ pluginId: "gmail", enabled: true, connectionId: "c1" }] }));
    expect(screen.getByLabelText("Account")).toHaveValue("c1");
  });

  it("'React to new email' shows under a connected Gmail and switching it saves only the trigger", async () => {
    const trigger = { name: "new_email", title: "React to new email", description: "When a new email arrives…", enabled: false, subscriberId: null, problem: null };
    const connected = { ...gmail, enabled: true, connectionId: "c1", triggers: [trigger] };
    api.routes["GET /api/v1/orgs/o1/bots/b1/tools"] = { status: 200, body: { plugins: [plugin({}), connected] } };
    api.routes["GET /api/v1/orgs/o1/connections"] = { status: 200, body: [account({})] };
    api.routes["PUT /api/v1/orgs/o1/bots/b1/tools/gmail/triggers/new_email"] = {
      status: 200,
      body: { plugins: [plugin({}), { ...connected, triggers: [{ ...trigger, enabled: true, subscriberId: "u1" }] }] },
    };
    const { user } = await open();

    const toggle = await screen.findByRole("switch", { name: "React to new email" });
    expect(toggle).not.toBeChecked();
    await user.click(toggle);
    await vi.waitFor(() => expect(screen.getByRole("switch", { name: "React to new email" })).toBeChecked());
    expect(api.sent.at(-1)).toEqual({ key: "PUT /api/v1/orgs/o1/bots/b1/tools/gmail/triggers/new_email", body: { enabled: true } });
    expect(screen.getByText(/comes to your chat with/)).toBeInTheDocument();
  });

  it("hides the trigger until Gmail has an account, and shows why a trigger is paused", async () => {
    const trigger = { name: "new_email", title: "React to new email", description: "", enabled: true, subscriberId: "u2", problem: "Paused: zara@example.com needs reconnecting first (Connect apps)." };
    api.routes["GET /api/v1/orgs/o1/bots/b1/tools"] = {
      status: 200,
      body: { plugins: [{ ...gmail, triggers: [trigger] }, { ...gmail, pluginId: "gmail2", name: "Mail two", enabled: true, connectionId: "c1", triggers: [trigger] }] },
    };
    api.routes["GET /api/v1/orgs/o1/connections"] = { status: 200, body: [account({})] };
    await open();

    expect(within(await screen.findByRole("article", { name: "Gmail" })).queryByRole("switch", { name: "React to new email" })).toBeNull();
    const two = screen.getByRole("article", { name: "Mail two" });
    expect(within(two).getByRole("switch", { name: "React to new email" })).toBeChecked();
    expect(within(two).getByText(/needs reconnecting/)).toBeInTheDocument();
    expect(within(two).getByText(/Switched on by another member/)).toBeInTheDocument();
  });

  it("shows the API's refusal", async () => {
    api.routes["GET /api/v1/orgs/o1/bots/b1/tools"] = { status: 200, body: { plugins: [gmail] } };
    api.routes["GET /api/v1/orgs/o1/connections"] = { status: 200, body: [account({})] };
    api.routes["PUT /api/v1/orgs/o1/bots/b1/tools"] = { status: 403, body: { detail: "Only that member can turn on their own account for a bot." } };
    const { user } = await open();

    await user.selectOptions(await screen.findByLabelText("Account"), "c1");
    expect(await screen.findByRole("alert")).toHaveTextContent("Only that member can turn on their own account for a bot.");
  });

  it("says so, with Try again, when the tools can't be loaded", async () => {
    api.routes["GET /api/v1/orgs/o1/bots/b1/tools"] = { status: 500, body: { detail: "Oops" } };
    await open();
    expect(await screen.findByText("Couldn't load Scout's tools.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
  it("an MCP server says how many tools wait for a review, and a member can't switch one with the organization's sign-in", async () => {
    api.routes["POST /api/v1/auth/sign-in"] = { status: 200, body: { ...apiMe, organizations: [{ ...apiOrg, role: "member" }] } };
    api.routes["GET /api/v1/orgs/o1/members"] = { status: 200, body: [{ ...apiMe.user, role: "member" }] };
    const tracker = plugin({
      pluginId: "mcp-1a2b3c4d", name: "Tracker", description: "Tools from the MCP server at https://mcp.example.com/mcp.", enabled: false, tools: [],
      mcp: { toolsWaiting: 2, problem: "Needs signing in again: an owner or admin can reconnect it on Connect apps.", orgAccount: true },
    });
    api.routes["GET /api/v1/orgs/o1/bots/b1/tools"] = { status: 200, body: { plugins: [plugin({}), tracker] } };
    api.routes["GET /api/v1/orgs/o1/connections"] = { status: 200, body: [] };
    await open();

    const card = await screen.findByRole("article", { name: "Tracker" });
    expect(within(card).getByText("2 tools to review")).toBeInTheDocument();
    expect(within(card).getByText(/until an owner or admin reviews them/)).toBeInTheDocument();
    expect(within(card).getByRole("status")).toHaveTextContent("Needs signing in again");
    expect(within(card).getByRole("switch", { name: "Use Tracker" })).toBeDisabled();
    expect(within(card).getByText(/only owners and admins switch it on or off/)).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Use Demo" })).toBeEnabled(); // other plugins as before
  });
});
