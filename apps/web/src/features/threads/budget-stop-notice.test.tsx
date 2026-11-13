import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Message } from "@/data/types";
import { renderUI } from "@/test/render";
import { MessageItem } from "./message-item";

const reply = (patch: Partial<Message>): Message => ({
  id: "m1", threadId: "t_inbox", author: { type: "bot", id: "b_inbox" }, parts: [], status: "error",
  createdAt: "2026-11-12T05:00:00Z", ...patch,
});

describe("a reply stopped by its budget", () => {
  it("says why and offers to raise the bot's budget or look at usage", () => {
    const error = "Inbox Manager reached its $40 monthly budget. Raise it in the bot's settings.";
    renderUI(<MessageItem message={reply({ error, errorCode: "budget" })} isGroup={false} />);
    expect(screen.getByText("Out of budget for this month")).toBeInTheDocument();
    expect(screen.getByText(error)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Usage & budgets" })).toHaveAttribute("href", "/settings/usage");
  });

  it("other failures stay a short line", () => {
    renderUI(<MessageItem message={reply({ error: "The model couldn't reply." })} isGroup={false} />);
    expect(screen.getByText("The model couldn't reply.")).toBeInTheDocument();
    expect(screen.queryByText("Out of budget for this month")).not.toBeInTheDocument();
  });
});
