import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { actions, getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { MemorySettings } from "@/features/settings/memory-settings";
import { BotMemories } from "./bot-memories";

const chief = () => getStoreSnapshot().bots.find((b) => b.id === "b_chief")!;
const memoriesList = () => screen.findByRole("list", { name: "What Chief remembers" });

describe("BotMemories", () => {
  it("lists what the bot remembers, with where it learned it", async () => {
    renderUI(<BotMemories bot={chief()} />);
    const list = await memoriesList();
    const items = within(list).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("The launch crew ships on Fridays");
    expect(items[0]).toHaveTextContent("From group chats");
    expect(items[1]).toHaveTextContent("From your chat");
  });

  it("searches as you type", async () => {
    const { user } = renderUI(<BotMemories bot={chief()} />);
    await memoriesList();
    await user.type(screen.getByLabelText("Search what Chief remembers"), "thursday");
    await waitFor(() => expect(screen.queryByText(/launch crew/)).not.toBeInTheDocument());
    expect(screen.getByText(/Thursdays after 2 PM/)).toBeInTheDocument();
  });

  it("forgets a memory", async () => {
    const { user } = renderUI(<BotMemories bot={chief()} />);
    await memoriesList();
    await user.click(screen.getByRole("button", { name: /Forget: Thursdays after 2 PM/ }));
    await waitFor(() => expect(screen.queryByText(/Thursdays after 2 PM/)).not.toBeInTheDocument());
  });

  it("corrects a memory", async () => {
    const { user } = renderUI(<BotMemories bot={chief()} />);
    await memoriesList();
    await user.click(screen.getByRole("button", { name: /Correct: Thursdays after 2 PM/ }));
    const box = screen.getByLabelText("What the bot should remember");
    await user.clear(box);
    await user.type(box, "Thursday mornings are for focus.");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Thursday mornings are for focus.")).toBeInTheDocument();
  });

  it("forget everything asks first, then empties the list", async () => {
    const { user } = renderUI(<BotMemories bot={chief()} />);
    await memoriesList();
    await user.click(screen.getByRole("button", { name: "Forget everything" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Make Chief forget everything?");
    await user.click(within(dialog).getByRole("button", { name: "Forget everything" }));
    expect(await screen.findByText("Chief hasn't remembered anything yet. It learns as you chat.")).toBeInTheDocument();
  });

  it("members can change only what the bot learned in their own DM, and can't forget everything", async () => {
    await actions.changeMemberRole("u_me", "member");
    renderUI(<BotMemories bot={chief()} />);
    await memoriesList();
    expect(screen.getByRole("button", { name: /Forget: Thursdays after 2 PM/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Forget: The launch crew/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Forget everything" })).not.toBeInTheDocument();
  });

  it("when memory is off on the server, it says why instead of listing", () => {
    const reason = "Memory is off on this server. Set MEMORY_ENABLED=true and add OPENAI_API_KEY to turn it on.";
    getStoreSnapshot().memoryStatus = { enabled: false, reason };
    renderUI(<BotMemories bot={chief()} />);
    expect(screen.getByRole("alert")).toHaveTextContent(reason);
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});

describe("MemorySettings", () => {
  it("shows the first bot's memories and switches bots", async () => {
    const { user } = renderUI(<MemorySettings />);
    expect(await memoriesList()).toBeInTheDocument();
    await user.click(screen.getByRole("combobox", { name: "Show memories of" }));
    await user.click(await screen.findByRole("option", { name: "Sales Outbound" }));
    const list = await screen.findByRole("list", { name: "What Sales Outbound remembers" });
    expect(list).toHaveTextContent("Don't contact anyone reached in the last 30 days.");
  });
});
