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
