import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
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
});
