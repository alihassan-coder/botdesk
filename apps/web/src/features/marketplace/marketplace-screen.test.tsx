import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderUI } from "@/test/render";
import { apiScout, apiTemplates, signInOnApi, withFakeApi } from "@/test/fake-api";
import { MarketplaceScreen } from "./marketplace-screen";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

describe("Marketplace in the demo", () => {
  it("shows how often each template was hired, and Chief", () => {
    renderUI(<MarketplaceScreen />);
    expect(screen.getByText("12.4k hires")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hire Chief" })).toBeInTheDocument();
  });

  it("says when a template's bot starts stricter than the organization's default", () => {
    renderUI(<MarketplaceScreen />);
    expect(screen.getAllByText("Starts at Read only")).toHaveLength(2); // Expense Clerk and Researcher
  });
});

describe("Marketplace on the API", () => {
  const api = withFakeApi();
  const researcher = {
    id: "researcher", name: "Researcher", role: "Research", category: "Research", description: "Cited reports.",
    instructions: "You research questions.", avatarColor: "orange", securityLevel: "read-only", plugins: [],
  };

  it("lists the API's templates, not the demo's, with the apps they work in", async () => {
    api.routes["GET /api/v1/templates"] = { status: 200, body: [...apiTemplates, researcher] };
    await signInOnApi();
    renderUI(<MarketplaceScreen />);
    expect(screen.getByRole("button", { name: "Hire Researcher" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hire Outbound SDR" })).not.toBeInTheDocument();
    expect(screen.getByText("Gmail")).toBeInTheDocument();
    expect(screen.getByText("Starts at Read only")).toBeInTheDocument();
  });

  it("doesn't show made-up hire counts, and says templates are starting points", async () => {
    await signInOnApi();
    renderUI(<MarketplaceScreen />);
    expect(screen.getByRole("button", { name: "Hire Inbox Zero" })).toBeInTheDocument();
    expect(screen.queryByText(/hires$/)).not.toBeInTheDocument();
    expect(screen.getByText(/Templates are starting points/)).toBeInTheDocument();
  });

  it("hires once however often you click, then opens the bot's chat", async () => {
    let answer = () => {};
    const slow = new Promise<void>((resolve) => (answer = resolve));
    const fetchFake = vi.mocked(fetch);
    const real = fetchFake.getMockImplementation()!;
    fetchFake.mockImplementation(async (url, init) => {
      if (String(url).endsWith("/templates/chief/hire")) await slow;
      return real(url, init);
    });
    api.routes["POST /api/v1/orgs/o1/templates/chief/hire"] = { status: 201, body: { ...apiScout, id: "b9", name: "Chief" } };
    api.routes["POST /api/v1/orgs/o1/threads/dm"] = { status: 200, body: { id: "t9", kind: "dm", title: "Chief", botId: "b9", participants: [], lastMessageAt: "2026-11-18T08:00:00Z", lastMessagePreview: "" } };
    await signInOnApi();
    const { user } = renderUI(<MarketplaceScreen />);
    await user.click(screen.getByRole("button", { name: "Hire Chief" }));
    expect(screen.getByRole("button", { name: "Hire Chief" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Hire Inbox Zero" })).toBeDisabled();
    answer();
    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/chat/t9"));
    expect(api.sent.filter((r) => r.key === "POST /api/v1/orgs/o1/templates/chief/hire")).toHaveLength(1);
  });

  it("says when the marketplace didn't load, with Try again", async () => {
    api.routes["GET /api/v1/templates"] = { status: 503, body: { detail: "Down" } };
    await signInOnApi();
    const { user } = renderUI(<MarketplaceScreen />);
    expect(screen.getByRole("alert")).toHaveTextContent("The marketplace didn't load.");
    api.routes["GET /api/v1/templates"] = { status: 200, body: apiTemplates };
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("button", { name: "Hire Chief" })).toBeInTheDocument();
  });
});
