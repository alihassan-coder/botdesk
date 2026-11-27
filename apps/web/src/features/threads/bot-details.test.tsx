import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { signInOnApi, withFakeApi } from "@/test/fake-api";
import { BotDetails } from "./bot-details";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), back: vi.fn(), replace: vi.fn() }) }));

const botNamed = (name: string) => getStoreSnapshot().bots.find((b) => b.name === name)!;

describe("BotDetails' routines tab in the demo", () => {
  it("lists the bot's routines with their switches", async () => {
    const bot = getStoreSnapshot().bots.find((b) => getStoreSnapshot().routines.some((r) => r.botId === b.id))!;
    const routine = getStoreSnapshot().routines.find((r) => r.botId === bot.id)!;
    const { user } = renderUI(<BotDetails bot={bot} />);
    await user.click(screen.getByRole("tab", { name: "Routines" }));
    expect(screen.getByRole("switch", { name: `Run ${routine.name}` })).toBeInTheDocument();
  });
});

describe("BotDetails' routines tab on the API", () => {
  const api = withFakeApi();

  it("lists the bot's routines with their schedule and switch", async () => {
    api.routes["GET /api/v1/orgs/o1/routines"] = {
      status: 200,
      body: [{
        id: "r1", botId: "b1", createdBy: "u1", name: "Morning digest", instructions: "Sum up.", cron: "0 9 * * *",
        timezone: "Asia/Karachi", enabled: true, securityLevel: null, disabledReason: null, lastRunAt: null,
        nextRunAt: "2026-11-16T04:00:00Z", lastResult: null, createdAt: "2026-11-12T08:00:00Z",
      }],
    };
    await signInOnApi();
    await vi.waitFor(() => expect(getStoreSnapshot().routinesLoading).toBe(false));
    const { user } = renderUI(<BotDetails bot={botNamed("Scout")} />);
    await user.click(screen.getByRole("tab", { name: "Routines" }));
    expect(screen.getByText("Every day at 9 AM (Asia/Karachi)")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Run Morning digest" })).toBeChecked();
  });
});

describe("BotDetails' security level", () => {
  it("says when the organization's ceiling caps the bot", async () => {
    const bot = getStoreSnapshot().bots.find((b) => b.securityLevel === "autonomous")!;
    renderUI(<BotDetails bot={bot} />);
    expect(screen.queryByText(/Capped at/)).not.toBeInTheDocument();

    await actions.setMaxSecurityLevel("ask-before-acting");

    expect(await screen.findByText("Capped at Ask before acting by the organization")).toBeInTheDocument();
  });
});

describe("BotDetails' computer", () => {
  it("says what the bot works on, and shows a cloud bot's computer in place of the browser", async () => {
    const bot = { ...botNamed("Chief"), computer: "cloud" as const };
    const { user } = renderUI(<BotDetails bot={bot} />);
    expect(screen.getByText("Files and a cloud computer")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Computer" }));
    expect(screen.getByRole("heading", { name: "Cloud computer" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Browser" })).not.toBeInTheDocument();
    expect(await screen.findByText("No computer yet")).toBeInTheDocument();
  });
});
