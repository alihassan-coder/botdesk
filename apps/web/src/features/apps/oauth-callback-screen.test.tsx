import { act, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { rememberOAuthReturn } from "@/lib/connections";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { OAuthCallbackScreen, RETURN_AFTER_MS } from "./oauth-callback-screen";

const router = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

beforeEach(() => router.replace.mockClear());

describe("The OAuth callback page", () => {
  it("says the account is connected, with a way back to Connect apps", () => {
    renderUI(<OAuthCallbackScreen result="connected" code={null} connector="gmail" />);
    expect(screen.getByText("Connected", { selector: "[data-slot=alert-title]" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Connect apps" })).toHaveAttribute("href", "/apps");
  });

  it("goes back to where Connect was pressed after a moment", () => {
    vi.useFakeTimers();
    rememberOAuthReturn("/chat/t1");
    renderUI(<OAuthCallbackScreen result="connected" code={null} connector="gmail" />);

    expect(screen.getByRole("link", { name: "Back to the chat" })).toHaveAttribute("href", "/chat/t1");
    act(() => vi.advanceTimersByTime(RETURN_AFTER_MS - 1));
    expect(router.replace).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(router.replace).toHaveBeenCalledWith("/chat/t1");
  });

  it("never goes back to another site, whatever was remembered", () => {
    vi.useFakeTimers();
    rememberOAuthReturn("//evil.com/phish");
    renderUI(<OAuthCallbackScreen result="connected" code={null} connector="gmail" />);

    expect(screen.getByRole("link", { name: "Back to Connect apps" })).toHaveAttribute("href", "/apps");
    act(() => vi.advanceTimersByTime(RETURN_AFTER_MS));
    expect(router.replace).toHaveBeenCalledWith("/apps");
  });

  it("stays when connecting failed, so the reason can be read, with the way back", () => {
    vi.useFakeTimers();
    rememberOAuthReturn("/chat/t1");
    renderUI(<OAuthCallbackScreen result="error" code="denied" connector={null} />);

    expect(screen.getByRole("link", { name: "Back to the chat" })).toHaveAttribute("href", "/chat/t1");
    act(() => vi.advanceTimersByTime(RETURN_AFTER_MS * 2));
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("says why nothing was connected when the person cancelled", () => {
    renderUI(<OAuthCallbackScreen result="error" code="denied" connector={null} />);
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    expect(screen.getByText("You cancelled signing in, so nothing was connected.")).toBeInTheDocument();
  });

  it("explains an expired or reused sign-in", () => {
    renderUI(<OAuthCallbackScreen result="error" code="expired" connector={null} />);
    expect(screen.getByText(/took too long or was already used/)).toBeInTheDocument();
  });

  it("shows the generic message for a code it doesn't know, never the code itself", () => {
    renderUI(<OAuthCallbackScreen result="error" code="provider_said_<b>no</b>" connector={null} />);
    expect(screen.getByText("Couldn't finish connecting the app. Try again.")).toBeInTheDocument();
    expect(screen.queryByText(/provider_said/)).not.toBeInTheDocument();
  });
});


describe("The OAuth callback page after an MCP server's sign-in", () => {
  const api = withFakeApi();

  it("says it's signed in and leads to Review tools, since nothing is offered before that", async () => {
    api.routes["GET /api/v1/orgs/o1/mcp-servers"] = {
      status: 200,
      body: [{
        id: "m1", pluginId: "mcp-1a2b3c4d", name: "Tracker", url: "https://mcp.example.com/mcp", authKind: "oauth", authHeader: null,
        status: "active", statusReason: null, lastCheckedAt: null, createdAt: "2026-11-18T08:00:00Z", createdBy: "u1", toolsHash: "h", toolsChanged: 1,
        tools: [{ name: "mcp-1a2b3c4d.echo", serverName: "echo", title: null, description: "Echoes.", annotations: {}, inputSchema: { type: "object" },
          outputSchema: null, state: "pending", enabled: false, risk: "external-send", previous: null }],
      }],
    };
    await signInOnApi();
    renderUI(<OAuthCallbackScreen result="connected" code={null} connector="mcp-1a2b3c4d" />);

    expect(await screen.findByText("Signed in to Tracker")).toBeInTheDocument();
    expect(screen.getByText(/1 tool to review\. No bot gets this MCP server's tools until an owner or admin has reviewed them/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review tools" })).toHaveAttribute("href", "/apps/mcp/m1");
    expect(screen.getByRole("link", { name: "Back to Connect apps" })).toHaveAttribute("href", "/apps");
    expect(router.replace).not.toHaveBeenCalled(); // the review comes first: it doesn't leave by itself
  });
});
