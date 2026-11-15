import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getStoreSnapshot } from "@/data/store";
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
  withFakeApi();

  it("says bots can't run on a schedule yet", async () => {
    await signInOnApi();
    const { user } = renderUI(<BotDetails bot={botNamed("Scout")} />);
    await user.click(screen.getByRole("tab", { name: "Routines" }));
    expect(screen.getByText("Bots can't run on a schedule yet. Routines arrive with the scheduler.")).toBeInTheDocument();
  });
});
