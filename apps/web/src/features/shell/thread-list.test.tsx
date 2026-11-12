import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { ThreadList } from "./thread-list";

// The list highlights the open chat from the URL; pretend the Inbox Manager chat is open.
vi.mock("next/navigation", () => ({ usePathname: () => "/chat/t_inbox" }));

describe("ThreadList", () => {
  it("groups conversations into Pinned, Bots and Groups", async () => {
    renderUI(<ThreadList />);

    const pinned = await screen.findByRole("region", { name: "Pinned" });
    expect(within(pinned).getByText("Chief")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Bots" })).getByText("Inbox Manager")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Groups" })).getByText("Launch crew")).toBeInTheDocument();
  });

  it("marks the open chat and links every row to its chat", async () => {
    renderUI(<ThreadList />);
    const open = await screen.findByRole("link", { current: "page" });
    expect(open).toHaveAttribute("href", "/chat/t_inbox");
  });

  it("shows what a bot is doing when it needs you, with the unread count", async () => {
    renderUI(<ThreadList />);
    const row = await screen.findByRole("link", { name: /Inbox Manager/ });
    expect(within(row).getByText("2 replies waiting for you")).toBeInTheDocument();
    expect(within(row).getByText("2")).toBeInTheDocument();
  });

  it("filters by search and says when nothing matches", async () => {
    const { rerender } = renderUI(<ThreadList query="sales" />);
    expect(await screen.findByText("Sales Outbound")).toBeInTheDocument();
    expect(screen.queryByText("Chief")).not.toBeInTheDocument();

    rerender(<ThreadList query="zzz" />);
    expect(screen.getByText("No bots or groups match “zzz”.")).toBeInTheDocument();
  });
});

describe("ThreadList with no bots", () => {
  it("points you to creating or hiring one", async () => {
    for (const bot of getStoreSnapshot().bots) await actions.removeBot(bot.id);
    renderUI(<ThreadList />);
    expect(await screen.findByText("No bots yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create a bot" })).toHaveAttribute("href", "/bots/new");
  });
});
