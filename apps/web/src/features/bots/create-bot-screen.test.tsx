import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { CreateBotScreen } from "./create-bot-screen";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, back: vi.fn() }) }));

describe("CreateBotScreen", () => {
  beforeEach(() => push.mockClear());

  it("asks for a name and a role before creating", async () => {
    const { user } = renderUI(<CreateBotScreen />);
    await user.click(screen.getByRole("button", { name: "Create bot" }));

    expect(screen.getByText("Give your bot a name.")).toBeInTheDocument();
    expect(screen.getByText("Say what job it does.")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("shows a live preview as you type", async () => {
    const { user } = renderUI(<CreateBotScreen />);
    await user.type(screen.getByLabelText("Name"), "Release Notes");
    await user.type(screen.getByLabelText("Role"), "Writing");

    expect(screen.getByText("Writing · @release-notes")).toBeInTheDocument();
  });

  it("a template fills the form", async () => {
    const { user } = renderUI(<CreateBotScreen />);
    await user.click(screen.getByRole("button", { name: "Recruiter" }));
    expect(screen.getByLabelText("Name")).toHaveValue("Recruiter");
    expect(screen.getByLabelText("Role")).toHaveValue("Recruiting");
  });

  it("creates the bot with your choices and opens its chat", async () => {
    const { user } = renderUI(<CreateBotScreen />);
    await user.type(screen.getByLabelText("Name"), "Release Notes");
    await user.type(screen.getByLabelText("Role"), "Writing");
    await user.click(screen.getByRole("radio", { name: "rose" }));
    await user.click(screen.getByLabelText(/Read only/));
    await user.click(screen.getByRole("button", { name: "Create bot" }));

    const bot = getStoreSnapshot().bots.find((b) => b.name === "Release Notes");
    expect(bot).toMatchObject({ role: "Writing", avatarColor: "rose", securityLevel: "read-only" });
    const thread = getStoreSnapshot().threads.find((t) => t.botId === bot?.id);
    expect(push).toHaveBeenCalledWith(`/chat/${thread?.id}`);
  });
});
