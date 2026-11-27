import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { apiScout, signInOnApi, withFakeApi } from "@/test/fake-api";
import { EditBotDialog } from "./edit-bot-dialog";

const chief = () => getStoreSnapshot().bots.find((b) => b.id === "b_chief")!;

describe("EditBotDialog", () => {
  it("owners and admins can change the budget", async () => {
    const { user } = renderUI(<EditBotDialog bot={chief()} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    const budget = screen.getByLabelText("Monthly budget (USD)");
    await user.clear(budget);
    await user.type(budget, "120");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(chief().monthlyBudgetUsd).toBe(120);
  });

  it("members see the budget but can't change it", async () => {
    await actions.changeMemberRole("u_me", "member");
    const { user } = renderUI(<EditBotDialog bot={chief()} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));

    const budget = screen.getByLabelText("Monthly budget (USD)");
    expect(budget).toHaveAttribute("readonly");
    expect(budget).toHaveAccessibleDescription("Only owners and admins can change budgets.");
  });
});

describe("EditBotDialog under the organization's ceiling", () => {
  it("offers only levels up to the ceiling", async () => {
    await actions.setMaxSecurityLevel("ask-before-acting");
    const { user } = renderUI(<EditBotDialog bot={chief()} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByRole("radio", { name: /^Autonomous/ })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /^Read only/ })).toBeEnabled();
  });

  it("a bot already above a lowered ceiling shows its own level and can still be saved", async () => {
    await actions.editBot("b_chief", { securityLevel: "autonomous" });
    await actions.setMaxSecurityLevel("read-only");
    const { user } = renderUI(<EditBotDialog bot={chief()} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByRole("radio", { name: /^Autonomous/ })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(chief().securityLevel).toBe("autonomous");
  });
});

describe("EditBotDialog's computer", () => {
  it("in the demo, a cloud computer is unavailable and says where the key goes", async () => {
    const { user } = renderUI(<EditBotDialog bot={chief()} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByRole("radio", { name: /^Files and a browser/ })).toBeChecked();
    const cloud = screen.getByRole("radio", { name: /^Files and a cloud computer/ });
    expect(cloud).toBeDisabled();
    expect(cloud).toHaveAccessibleDescription("A cloud computer needs an Orgo key. An owner or admin adds one in Settings → Computers.");
    expect(screen.getByRole("link", { name: "Settings → Computers" })).toHaveAttribute("href", "/settings/computers");
  });
});

describe("EditBotDialog's computer on the API", () => {
  const api = withFakeApi();
  const scout = () => getStoreSnapshot().bots.find((b) => b.id === "b1")!;
  const patches = () => api.sent.filter((s) => s.key === "PATCH /api/v1/orgs/o1/bots/b1").map((s) => s.body as Record<string, unknown>);

  async function open() {
    api.routes["GET /api/v1/orgs/o1/computer-provider"] = { status: 200, body: { provider: "orgo", keyHint: "abcd", checkedAt: null, status: "ok" } };
    await signInOnApi();
    const { user } = renderUI(<EditBotDialog bot={scout()} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await vi.waitFor(() => expect(screen.getByRole("radio", { name: /^Files and a cloud computer/ })).toBeEnabled());
    return user;
  }

  it("switches the bot to its own cloud computer", async () => {
    api.routes["PATCH /api/v1/orgs/o1/bots/b1"] = { status: 200, body: { ...apiScout, computer: "cloud" } };
    const user = await open();
    await user.click(screen.getByRole("radio", { name: /^Files and a cloud computer/ }));
    expect(screen.getByText("It loses its browser tools: the cloud computer has a browser of its own.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await vi.waitFor(() => expect(scout().computer).toBe("cloud"));
    expect(patches()[0]).toMatchObject({ computer: "cloud" });
  });

  it("sends the computer only when it changed, and shows a refusal in the form", async () => {
    api.routes["PATCH /api/v1/orgs/o1/bots/b1"] = { status: 400, body: { detail: "An owner or admin can add an Orgo key in Settings → Computers." } };
    const user = await open();
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("An owner or admin can add an Orgo key in Settings → Computers.");
    expect(patches()[0]).not.toHaveProperty("computer");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
