import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { browser } from "@/lib/navigate";
import { renderUI } from "@/test/render";
import { apiOrg, apiScout, signInOnApi, withFakeApi } from "@/test/fake-api";
import { BotStep } from "./bot-step";
import { GmailStep } from "./gmail-step";
import { KeyStep } from "./key-step";
import { OrgStep } from "./org-step";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));

/* A brand-new organization on the API: Zara owns it, and it has no bots or chats yet. */
const notConnected = { connected: false, source: null, keyHint: null, status: null, lastVerifiedAt: null, baseUrl: null };
const openai = { id: "openai", kind: "openai", name: "OpenAI", hint: "GPT models.", ...notConnected };
const connectedOpenai = { ...openai, connected: true, source: "org", keyHint: "abcd", status: "ok", lastVerifiedAt: "2026-11-17T10:00:00Z" };
const gmail = { id: "gmail", name: "Gmail", version: "0.1.0", description: "Your mail.", authType: "oauth2", setup: "ready", accessLevels: ["read", "full"], defaultAccess: "full", tools: [] };
const chief = { ...apiScout, id: "b2", name: "Chief", handle: "chief", role: "Chief of staff" };
const chiefDm = { id: "t2", kind: "dm", title: "Chief", botId: "b2", participants: [{ type: "user", id: "u1" }, { type: "bot", id: "b2" }], lastMessageAt: "2026-11-17T10:00:00Z", lastMessagePreview: "" };

const api = withFakeApi();
beforeEach(() => {
  Object.assign(api.routes, {
    "GET /api/v1/orgs/o1/bots": { status: 200, body: [] },
    "GET /api/v1/orgs/o1/threads": { status: 200, body: [] },
    "GET /api/v1/orgs/o1/providers": { status: 200, body: [openai] },
    "GET /api/v1/orgs/o1/models": { status: 200, body: { models: [], errors: [] } },
  });
});

describe("Step 1: name your organization", () => {
  it("is prefilled, saves a new name and moves on", async () => {
    api.routes["PATCH /api/v1/orgs/o1"] = { status: 200, body: { ...apiOrg, name: "Zara Labs" } };
    await signInOnApi();
    const onNext = vi.fn();
    const { user } = renderUI(<OrgStep onNext={onNext} />);

    const name = screen.getByLabelText("Organization name");
    expect(name).toHaveValue("Zara's team");
    await user.clear(name);
    await user.type(name, "Zara Labs");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await vi.waitFor(() => expect(onNext).toHaveBeenCalled());
    expect(api.sent.find((r) => r.key === "PATCH /api/v1/orgs/o1")?.body).toEqual({ name: "Zara Labs" });
    expect(getStoreSnapshot().org.name).toBe("Zara Labs");
  });

  it("shows the API's reason and stays when saving fails", async () => {
    api.routes["PATCH /api/v1/orgs/o1"] = { status: 400, body: { detail: "That name is too long." } };
    await signInOnApi();
    const onNext = vi.fn();
    const { user } = renderUI(<OrgStep onNext={onNext} />);

    await user.type(screen.getByLabelText("Organization name"), "!");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("That name is too long.")).toBeInTheDocument();
    expect(onNext).not.toHaveBeenCalled();
  });

  it("Skip moves on without saving", async () => {
    await signInOnApi();
    const onNext = vi.fn();
    const { user } = renderUI(<OrgStep onNext={onNext} />);
    await user.click(screen.getByRole("button", { name: "Skip" }));
    expect(onNext).toHaveBeenCalled();
    expect(api.sent.some((r) => r.key.startsWith("PATCH"))).toBe(false);
  });
});

describe("Step 2: add an AI key", () => {
  it("adds a key with the Models & keys dialog, then Continue unlocks", async () => {
    api.routes["PUT /api/v1/orgs/o1/providers/openai"] = { status: 200, body: connectedOpenai };
    await signInOnApi();
    const onNext = vi.fn();
    const { user } = renderUI(<KeyStep onNext={onNext} />);

    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Add key for OpenAI" }));
    await user.type(screen.getByLabelText("API key"), "sk-proj-1234567890abcd");
    // After saving, the store reloads the catalogue, which now has the key.
    api.routes["GET /api/v1/orgs/o1/providers"] = { status: 200, body: [connectedOpenai] };
    await user.click(screen.getByRole("button", { name: "Check and save" }));

    const providers = screen.getByRole("list", { name: "Providers" });
    expect(await within(providers).findByText("Connected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(onNext).toHaveBeenCalled();
  });

  it("shows why a key didn't work, in the dialog", async () => {
    api.routes["PUT /api/v1/orgs/o1/providers/openai"] = { status: 400, body: { detail: "OpenAI says this key is not valid." } };
    await signInOnApi();
    const { user } = renderUI(<KeyStep onNext={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Add key for OpenAI" }));
    await user.type(screen.getByLabelText("API key"), "sk-wrong");
    await user.click(screen.getByRole("button", { name: "Check and save" }));
    expect(await screen.findByText("OpenAI says this key is not valid.")).toBeInTheDocument();
  });

  it("can be skipped: bots use a stand-in reply", async () => {
    await signInOnApi();
    const onNext = vi.fn();
    const { user } = renderUI(<KeyStep onNext={onNext} />);
    await user.click(screen.getByRole("button", { name: "Skip — bots will use a stand-in reply" }));
    expect(onNext).toHaveBeenCalled();
  });
});

describe("Step 3: hire your first bot", () => {
  it("recommends Chief plus one more, and hiring gives back the bot's DM", async () => {
    api.routes["POST /api/v1/orgs/o1/bots"] = { status: 201, body: chief };
    api.routes["POST /api/v1/orgs/o1/threads/dm"] = { status: 200, body: chiefDm };
    await signInOnApi();
    const onHired = vi.fn();
    const onNext = vi.fn();
    const { user } = renderUI(<BotStep onNext={onNext} onHired={onHired} onLeave={vi.fn()} />);

    expect(screen.getByText("Recommended")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hire Inbox Zero" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Hire Chief" }));

    expect(await screen.findByText("Hired")).toBeInTheDocument();
    expect(onHired).toHaveBeenCalledWith("t2");
    expect(api.sent.find((r) => r.key === "POST /api/v1/orgs/o1/bots")?.body).toMatchObject({ name: "Chief", role: "Chief of staff" });
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(onNext).toHaveBeenCalled();
  });

  it("says why hiring failed", async () => {
    api.routes["POST /api/v1/orgs/o1/bots"] = { status: 403, body: { detail: "Your plan allows 0 bots." } };
    await signInOnApi();
    const onHired = vi.fn();
    const { user } = renderUI(<BotStep onNext={vi.fn()} onHired={onHired} onLeave={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Hire Chief" }));
    expect(await screen.findByText("Your plan allows 0 bots.")).toBeInTheDocument();
    expect(onHired).not.toHaveBeenCalled();
  });

  it("can be skipped, or left to build a bot from scratch", async () => {
    await signInOnApi();
    const onNext = vi.fn();
    const onLeave = vi.fn();
    const { user } = renderUI(<BotStep onNext={onNext} onHired={vi.fn()} onLeave={onLeave} />);
    expect(screen.getByRole("link", { name: "Create one from scratch" })).toHaveAttribute("href", "/bots/new");
    await user.click(screen.getByRole("button", { name: "Skip" }));
    expect(onNext).toHaveBeenCalled();
  });
});

describe("Step 4: connect Gmail", () => {
  let leave: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    leave = vi.spyOn(browser, "leaveFor").mockImplementation(() => {});
    api.routes["GET /api/v1/orgs/o1/connections"] = { status: 200, body: [] };
  });
  afterEach(() => leave.mockRestore());

  it("signs in with Google through the Connect apps dialog, marking setup done first", async () => {
    api.routes["GET /api/v1/orgs/o1/connectors"] = { status: 200, body: [gmail] };
    api.routes["POST /api/v1/orgs/o1/connections/oauth/start"] = { status: 200, body: { authorizeUrl: "https://accounts.example/authorize" } };
    await signInOnApi();
    const onLeave = vi.fn();
    const { user } = renderUI(<GmailStep onFinish={vi.fn()} onLeave={onLeave} />);

    await user.click(await screen.findByRole("button", { name: "Connect Gmail" }));
    expect(onLeave).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Continue to Gmail" }));
    await vi.waitFor(() => expect(leave).toHaveBeenCalledWith("https://accounts.example/authorize"));
  });

  it("says when Gmail isn't set up on this server, links the guide, and can be skipped", async () => {
    api.routes["GET /api/v1/orgs/o1/connectors"] = { status: 200, body: [{ ...gmail, setup: "not-configured" }] };
    await signInOnApi();
    const onFinish = vi.fn();
    const { user } = renderUI(<GmailStep onFinish={onFinish} onLeave={vi.fn()} />);

    expect(await screen.findByText(/Not set up on this server/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "How to set it up" })).toHaveAttribute("href", expect.stringContaining("google-oauth.md"));
    expect(screen.queryByRole("button", { name: "Connect Gmail" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Skip for now" }));
    expect(onFinish).toHaveBeenCalled();
  });

  it("offers Try again when the apps don't load", async () => {
    api.routes["GET /api/v1/orgs/o1/connectors"] = { status: 500, body: { detail: "Boom" } };
    await signInOnApi();
    renderUI(<GmailStep onFinish={vi.fn()} onLeave={vi.fn()} />);
    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
