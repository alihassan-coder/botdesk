import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Message } from "@/data/types";
import { renderUI } from "@/test/render";
import { MessageItem } from "./message-item";

const at = "2026-11-15T05:00:00Z";

describe("messages from BotDesk and from bots working together", () => {
  it("a chain-stopped notice shows as a status line, with no author", () => {
    const notice: Message = {
      id: "n1", threadId: "t_launch", author: { type: "system", id: "system" }, createdAt: at,
      parts: [{ type: "text", text: "Stopped a chain of bot replies after 3 hops." }],
    };
    renderUI(<MessageItem message={notice} isGroup />);

    expect(screen.getByRole("status")).toHaveTextContent("Stopped a chain of bot replies after 3 hops.");
    expect(screen.queryByText("BotDesk")).not.toBeInTheDocument();
  });

  it("a routine's notices: the Created card links to the routines page; its run's trigger is a status line", () => {
    const created: Message = {
      id: "n2", threadId: "t_chief", author: { type: "system", id: "system" }, createdAt: at,
      parts: [{ type: "routine-created", routineId: "r9", name: "Morning digest" }],
    };
    const trigger: Message = {
      id: "n3", threadId: "t_chief", author: { type: "system", id: "system" }, createdAt: at,
      parts: [{ type: "text", text: "Routine: Morning digest" }],
    };
    renderUI(
      <>
        <MessageItem message={created} isGroup={false} />
        <MessageItem message={trigger} isGroup={false} />
      </>,
    );

    expect(screen.getByRole("link", { name: /Created a routine: Morning digest/ })).toHaveAttribute("href", "/routines");
    expect(screen.getByText("Routine: Morning digest")).toBeInTheDocument();
  });

  it("in a DM, a guest's reply says which bot wrote it; the DM's own bot's doesn't", () => {
    const from = (botId: string, text: string): Message => ({
      id: `m-${botId}`, threadId: "t_chief", author: { type: "bot", id: botId }, createdAt: at, status: "complete",
      parts: [{ type: "text", text }],
    });
    renderUI(
      <>
        <MessageItem message={from("b_inbox", "Inbox summary")} isGroup={false} dmBotId="b_chief" />
        <MessageItem message={from("b_chief", "Thanks, Inbox")} isGroup={false} dmBotId="b_chief" />
      </>,
    );

    expect(screen.getByText("Inbox Manager")).toBeInTheDocument();
    expect(screen.queryByText("Chief")).not.toBeInTheDocument();
  });
});
