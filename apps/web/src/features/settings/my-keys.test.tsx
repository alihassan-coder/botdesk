import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { apiMe, apiOrg, signInOnApi, withFakeApi } from "@/test/fake-api";
import { MyKeys } from "./my-keys";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const none = { source: null, keyHint: null, status: null, lastVerifiedAt: null, baseUrl: null };
const openai = { id: "openai", kind: "openai", name: "OpenAI", hint: "GPT models.", connected: false, ...none };
const groq = { id: "groq", kind: "groq", name: "Groq", hint: "Fast.", connected: false, ...none };
const mineOpenai = { ...openai, connected: true, source: "member", keyHint: "abcd", status: "ok", lastVerifiedAt: "2026-11-17T10:00:00Z" };

/** A provider's card, once the list has loaded. */
const card = async (name: string) => within((await screen.findByText(name, { selector: "p" })).closest("li")!);

describe("My keys, on the API", () => {
  const api = withFakeApi();

  beforeEach(async () => {
    api.routes["GET /api/v1/orgs/o1/me/providers"] = { status: 200, body: [openai, groq] };
    api.routes["GET /api/v1/orgs/o1/providers"] = { status: 200, body: [] };
    api.routes["GET /api/v1/orgs/o1/models"] = { status: 200, body: { models: [], errors: [] } };
  });

  it("saves your own key, then shows only its last 4 characters", async () => {
    await signInOnApi();
    api.routes["PUT /api/v1/orgs/o1/me/providers/openai"] = { status: 200, body: mineOpenai };
    const { user } = renderUI(<MyKeys />);

    await user.click((await card("OpenAI")).getByRole("button", { name: "Add your key" }));
    expect(screen.getByRole("dialog", { name: "Add your OpenAI key" })).toHaveTextContent("Only you see it");
    await user.type(screen.getByLabelText("API key"), "sk-proj-1234567890abcd");
    await user.click(screen.getByRole("button", { name: "Check and save" }));

    expect(await (await card("OpenAI")).findByText(/••••abcd/)).toBeInTheDocument();
    expect(api.sent.find((r) => r.key === "PUT /api/v1/orgs/o1/me/providers/openai")?.body).toEqual({ apiKey: "sk-proj-1234567890abcd" });
    expect(JSON.stringify(getStoreSnapshot())).not.toContain("sk-proj-1234567890abcd"); // only the hint is kept
    expect((await card("Groq")).getByRole("button", { name: "Add your key" })).toBeInTheDocument();
  });

  it("shows why a key didn't work, and keeps the dialog open", async () => {
    await signInOnApi();
    api.routes["PUT /api/v1/orgs/o1/me/providers/openai"] = { status: 400, body: { detail: "That key didn't work: 401: Incorrect API key provided." } };
    const { user } = renderUI(<MyKeys />);

    await user.click((await card("OpenAI")).getByRole("button", { name: "Add your key" }));
    await user.type(screen.getByLabelText("API key"), "sk-wrong-1234567890");
    await user.click(screen.getByRole("button", { name: "Check and save" }));

    expect(await screen.findByText("That key didn't work: 401: Incorrect API key provided.")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("removes your key", async () => {
    api.routes["GET /api/v1/orgs/o1/me/providers"] = { status: 200, body: [mineOpenai, groq] };
    api.routes["DELETE /api/v1/orgs/o1/me/providers/openai"] = { status: 204 };
    await signInOnApi();
    const { user } = renderUI(<MyKeys />);

    await user.click((await card("OpenAI")).getByRole("button", { name: "Remove" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Remove" }));

    expect(await (await card("OpenAI")).findByRole("button", { name: "Add your key" })).toBeInTheDocument();
    expect(api.sent.some((r) => r.key === "DELETE /api/v1/orgs/o1/me/providers/openai")).toBe(true);
  });

  it("members manage their own keys too", async () => {
    api.routes["POST /api/v1/auth/sign-in"] = { status: 200, body: { ...apiMe, organizations: [{ ...apiOrg, role: "member" }] } };
    await signInOnApi();
    renderUI(<MyKeys />);
    expect((await card("OpenAI")).getByRole("button", { name: "Add your key" })).toBeEnabled();
  });

  it("switching organizations shows that organization's keys", async () => {
    api.routes["POST /api/v1/auth/sign-in"] = { status: 200, body: { ...apiMe, organizations: [apiOrg, { ...apiOrg, id: "o2", name: "Acme" }] } };
    api.routes["GET /api/v1/orgs/o2/me/providers"] = { status: 200, body: [mineOpenai, groq] };
    await signInOnApi();
    renderUI(<MyKeys />);
    expect(await (await card("OpenAI")).findByRole("button", { name: "Add your key" })).toBeInTheDocument();

    await actions.switchOrg("o2");

    expect(await (await card("OpenAI")).findByText(/••••abcd/)).toBeInTheDocument();
  });
});

describe("My keys, in the demo", () => {
  it("lists the built-in providers and saves a key locally", async () => {
    const { user } = renderUI(<MyKeys />);
    await user.click((await card("Groq")).getByRole("button", { name: "Add your key" }));
    await user.type(screen.getByLabelText("API key"), "gsk_1234567890wxyz");
    await user.click(screen.getByRole("button", { name: "Check and save" }));
    expect(await (await card("Groq")).findByText(/••••wxyz/)).toBeInTheDocument();
    expect(screen.queryByText("Custom", { selector: "p" })).not.toBeInTheDocument();
  });
});
