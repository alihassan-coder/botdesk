import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { actions } from "@/data/store";
import { renderUI } from "@/test/render";
import { apiMe, apiOrg, signInOnApi, withFakeApi } from "@/test/fake-api";
import { MemorySettings } from "./memory-settings";

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { success: (m: string) => toastSuccess(m), error: (m: string) => toastError(m) } }));

beforeEach(() => {
  toastSuccess.mockClear();
  toastError.mockClear();
});

const card = () => within(screen.getByRole("region", { name: "Memory key" }));

/** One paste instead of a key press per character, so the test stays quick. */
async function pasteKey(user: UserEvent, key: string) {
  const field = card().getByLabelText("API key");
  await user.clear(field);
  await user.paste(key);
}

describe("Settings → Memory's key, in the demo", () => {
  it("starts with none, says why a key didn't work under the field, then shows only the last 4 of a good one", async () => {
    const { user } = renderUI(<MemorySettings />);
    expect(card().getByText("No memory key")).toBeInTheDocument();
    expect(screen.getByText(/used only for bots' memory: remembering what they learn and recalling it later, never for replies/)).toBeInTheDocument();

    await user.click(card().getByRole("button", { name: "Add key" }));
    expect(card().getByRole("radio", { name: /OpenAI/ })).toBeChecked();
    await user.click(card().getByRole("button", { name: "Check and save" }));
    expect(card().getByRole("alert")).toHaveTextContent("Paste your OpenAI API key.");

    await pasteKey(user, "bad-key-123456");
    await user.click(card().getByRole("button", { name: "Check and save" }));
    expect(await card().findByRole("alert")).toHaveTextContent("That key didn't work: 401 Unauthorized.");
    expect(card().getByLabelText("API key")).toHaveAttribute("aria-invalid", "true");

    await pasteKey(user, "sk-proj-1234abcd");
    await user.click(card().getByRole("button", { name: "Check and save" }));
    expect(await card().findByText("OpenAI")).toBeInTheDocument();
    expect(card().getByText(/Key ••••abcd/)).toBeInTheDocument();
    expect(card().queryByText(/sk-proj/)).not.toBeInTheDocument();
    expect(card().getByRole("button", { name: "Change" })).toHaveFocus();
    expect(toastSuccess).toHaveBeenCalledWith("Memory now uses your OpenAI key");
  });

  it("members see the key but can't change it", async () => {
    await actions.saveMemoryKey("gemini", "AIza-demo-9876wxyz");
    await actions.changeMemberRole("u_me", "member");
    renderUI(<MemorySettings />);
    expect(card().getByText("Google Gemini")).toBeInTheDocument();
    expect(card().getByText(/Key ••••wxyz/)).toBeInTheDocument();
    expect(card().queryByRole("button", { name: "Change" })).not.toBeInTheDocument();
    expect(card().queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    expect(card().getByText("Only owners and admins can change the memory key.")).toBeInTheDocument();
  });
});

describe("Settings → Memory's key, on the API", () => {
  const api = withFakeApi();
  const KEY = "/api/v1/orgs/o1/memory-key";
  const STATUS = "/api/v1/orgs/o1/memory/status";
  const saved = { provider: "openai", keyHint: "abcd", checkedAt: "2026-11-26T08:00:00Z" };

  beforeEach(() => {
    api.routes["GET /api/v1/orgs/o1/bots/b1/memories"] = { status: 200, body: [] };
  });

  it("saves a Gemini key, sending it once, and memory turns on with it", async () => {
    api.routes[`GET ${KEY}`] = { status: 200, body: { provider: null, keyHint: null, checkedAt: null } };
    api.routes[`GET ${STATUS}`] = { status: 200, body: { enabled: false, reason: "Memory is off on this server." } };
    api.routes[`PUT ${KEY}`] = { status: 200, body: { provider: "gemini", keyHint: "wxyz", checkedAt: "2026-11-26T08:00:00Z" } };
    await signInOnApi();
    const { user } = renderUI(<MemorySettings />);
    expect(await screen.findByText("Memory is off on this server.")).toBeInTheDocument();

    await user.click(await card().findByRole("button", { name: "Add key" }));
    await user.click(card().getByRole("radio", { name: /Google Gemini/ }));
    await pasteKey(user, "AIza-test-1234wxyz");
    api.routes[`GET ${STATUS}`] = { status: 200, body: { enabled: true, reason: null } };
    await user.click(card().getByRole("button", { name: "Check and save" }));

    expect(await card().findByText("Google Gemini")).toBeInTheDocument();
    expect(card().getByText(/Key ••••wxyz/)).toBeInTheDocument();
    expect(api.sent.find((s) => s.key === `PUT ${KEY}`)?.body).toEqual({ provider: "gemini", apiKey: "AIza-test-1234wxyz" });
    // Whether memory is on can change with the key, so the status is asked for again after the save.
    const keys = api.sent.map((s) => s.key);
    expect(keys.lastIndexOf(`GET ${STATUS}`)).toBeGreaterThan(keys.indexOf(`PUT ${KEY}`));
    await vi.waitFor(() => expect(screen.queryByText("Memory is off on this server.")).not.toBeInTheDocument());
  });

  it("shows the API's reason under the key when it didn't work, and keeps the form open", async () => {
    api.routes[`GET ${KEY}`] = { status: 200, body: saved };
    api.routes[`PUT ${KEY}`] = { status: 400, body: { detail: "That key didn't work: Incorrect API key provided." } };
    await signInOnApi();
    const { user } = renderUI(<MemorySettings />);
    await user.click(await card().findByRole("button", { name: "Change" }));
    await pasteKey(user, "sk-wrong-00000000");
    await user.click(card().getByRole("button", { name: "Check and save" }));

    expect(await card().findByRole("alert")).toHaveTextContent("That key didn't work: Incorrect API key provided.");
    expect(card().getByRole("form", { name: "Change the memory key" })).toBeInTheDocument();
    expect(card().getByText(/Key ••••abcd/)).toBeInTheDocument();
  });

  it("removes the key only once you say so, then asks whether memory is still on", async () => {
    api.routes[`GET ${KEY}`] = { status: 200, body: saved };
    api.routes[`DELETE ${KEY}`] = { status: 204 };
    await signInOnApi();
    const { user } = renderUI(<MemorySettings />);

    await user.click(await card().findByRole("button", { name: "Remove" }));
    const dialog = within(screen.getByRole("alertdialog", { name: "Remove the memory key?" }));
    expect(dialog.getByText(/found again with another OpenAI key/)).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Keep it" }));
    expect(api.sent.some((s) => s.key === `DELETE ${KEY}`)).toBe(false);

    await user.click(card().getByRole("button", { name: "Remove" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Remove" }));
    expect(await card().findByText("No memory key")).toBeInTheDocument();
    const keys = api.sent.map((s) => s.key);
    expect(keys.lastIndexOf(`GET ${STATUS}`)).toBeGreaterThan(keys.indexOf(`DELETE ${KEY}`));
    expect(toastSuccess).toHaveBeenCalledWith("Memory key removed");
  });

  it("members see which key memory uses, without Change or Remove", async () => {
    api.routes["POST /api/v1/auth/sign-in"] = { status: 200, body: { ...apiMe, organizations: [{ ...apiOrg, role: "member" }] } };
    api.routes["GET /api/v1/orgs/o1/members"] = { status: 200, body: [{ ...apiMe.user, role: "member" }] };
    api.routes[`GET ${KEY}`] = { status: 200, body: saved };
    await signInOnApi();
    renderUI(<MemorySettings />);
    expect(await card().findByText("OpenAI")).toBeInTheDocument();
    expect(card().queryByRole("button", { name: "Change" })).not.toBeInTheDocument();
    expect(card().queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    expect(card().getByText("Only owners and admins can change the memory key.")).toBeInTheDocument();
  });
});
