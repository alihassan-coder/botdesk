import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Button } from "@/components/ui/button";
import { actions } from "@/data/store";
import type { ModelProvider } from "@/data/types";
import { renderUI } from "@/test/render";
import { AddKeyDialog } from "./add-key-dialog";

const gpuBox: ModelProvider = {
  id: "custom-gpu-box", kind: "custom", name: "GPU box", hint: "Any OpenAI-compatible server.", connected: true,
  source: "org", keyHint: "9f3e", status: "ok", baseUrl: "https://gpu.acme.dev/v1",
};
const groq: ModelProvider = { id: "groq", kind: "groq", name: "Groq", hint: "Fast open models, and it has a free tier.", connected: false };

afterEach(() => {
  vi.restoreAllMocks();
});

function openFor(provider?: ModelProvider) {
  const rendered = renderUI(<AddKeyDialog provider={provider} trigger={<Button>Open</Button>} />);
  return { ...rendered, open: () => rendered.user.click(screen.getByRole("button", { name: "Open" })) };
}

describe("AddKeyDialog", () => {
  it("hides the key by default, shows it on request, and says Checking… while the API tries it", async () => {
    let finish: (value: { ok: true }) => void = () => {};
    const save = vi.spyOn(actions, "saveProviderKey").mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const { user, open } = openFor(groq);
    await open();

    const field = screen.getByLabelText("API key");
    expect(field).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Show key" }));
    expect(field).toHaveAttribute("type", "text");

    await user.type(field, "gsk_live_1234567890wxyz");
    await user.click(screen.getByRole("button", { name: "Check and save" }));
    expect(await screen.findByRole("button", { name: "Checking…" })).toBeDisabled();
    expect(save).toHaveBeenCalledWith("groq", { apiKey: "gsk_live_1234567890wxyz" });

    finish({ ok: true });
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows why a key didn't work and keeps the dialog open", async () => {
    vi.spyOn(actions, "saveProviderKey").mockResolvedValue({ ok: false, error: "That key didn't work: 401: Invalid API Key" });
    const { user, open } = openFor(groq);
    await open();
    await user.type(screen.getByLabelText("API key"), "gsk_wrong");
    await user.click(screen.getByRole("button", { name: "Check and save" }));

    expect(await screen.findByText("That key didn't work: 401: Invalid API Key")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Check and save" })).toBeEnabled();
  });

  it("a custom server needs a name and an http(s) base URL; its key is optional", async () => {
    const save = vi.spyOn(actions, "saveProviderKey").mockResolvedValue({ ok: true });
    const { user, open } = openFor();
    await open();
    const submit = screen.getByRole("button", { name: "Check and save" });

    await user.type(screen.getByLabelText("Name"), "Ollama");
    await user.type(screen.getByLabelText("Base URL"), "localhost:11434");
    expect(submit).toBeDisabled();
    await user.clear(screen.getByLabelText("Base URL"));
    await user.type(screen.getByLabelText("Base URL"), "http://localhost:11434/v1");
    expect(submit).toBeEnabled();

    await user.click(submit);
    expect(save).toHaveBeenCalledWith("custom", { apiKey: "", baseUrl: "http://localhost:11434/v1", label: "Ollama" });
  });

  it("editing a custom server keeps its key when left blank, but asks again when the URL changes", async () => {
    const save = vi.spyOn(actions, "saveProviderKey").mockResolvedValue({ ok: true });
    const { user, open } = openFor(gpuBox);
    await open();
    expect(screen.getByText(/Leave blank to keep the current key \(••••9f3e\)/)).toBeInTheDocument();

    const url = screen.getByLabelText("Base URL");
    await user.clear(url);
    await user.type(url, "https://new-gpu.acme.dev/v1");
    expect(screen.getByText(/You changed the URL, so paste the key again/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check and save" })).toBeDisabled();

    await user.click(screen.getByLabelText(/This server needs no key/));
    expect(screen.getByLabelText("API key (optional)")).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Check and save" }));
    expect(save).toHaveBeenCalledWith("custom-gpu-box", { apiKey: "", baseUrl: "https://new-gpu.acme.dev/v1", label: "GPU box", noKey: true });
  });

  it("renaming a custom server with the key left blank sends no key, so the API keeps the saved one", async () => {
    const save = vi.spyOn(actions, "saveProviderKey").mockResolvedValue({ ok: true });
    const { user, open } = openFor(gpuBox);
    await open();
    await user.type(screen.getByLabelText("Name"), " 2");
    await user.click(screen.getByRole("button", { name: "Check and save" }));
    expect(save).toHaveBeenCalledWith("custom-gpu-box", { apiKey: "", baseUrl: "https://gpu.acme.dev/v1", label: "GPU box 2" });
  });
});
