import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Message } from "@/data/types";
import { renderUI } from "@/test/render";
import { MessageParts } from "./message-parts";

/** One message carrying every part type, so a missing or broken card shows up here. */
const everyPart: Message = {
  id: "m_test",
  threadId: "t_chief",
  author: { type: "bot", id: "b_chief" },
  createdAt: "2026-11-12T04:00:00Z",
  parts: [
    { type: "text", text: "Hello @sales" },
    { type: "reasoning", text: "Thinking it through.", durationSec: 3 },
    { type: "work-log", title: "Tonight's run", items: [{ label: "Inbox", detail: "12 flagged", done: true }, { label: "Send", done: false }] },
    { type: "computer-task", title: "Queue drafts", app: "LinkedIn", status: "needs-takeover", stepCount: 4 },
    { type: "approval", approvalId: "a_1" },
    { type: "question", question: "Archive cold emails?", options: ["Yes", "No"] },
    { type: "routine-created", routineId: "r_1", name: "Overnight outbound" },
    { type: "file", name: "report.csv", mime: "text/csv", sizeBytes: 18_204 },
    { type: "handoff", fromBotId: "b_chief", toBotId: "b_sales", task: "Draft openers" },
  ],
};

describe("MessageParts", () => {
  it("renders every kind of card", () => {
    renderUI(<MessageParts message={everyPart} isOwn={false} />);

    expect(screen.getByText("@sales")).toBeInTheDocument(); // text, with the mention highlighted
    expect(screen.getByText("Thought for 3s")).toBeInTheDocument(); // reasoning
    expect(screen.getByText("Tonight's run")).toBeInTheDocument(); // work log
    expect(screen.getByLabelText("Not done yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Take over" })).toBeInTheDocument(); // computer task
    expect(screen.getByText("Send reply to Vicky (Globex)")).toBeInTheDocument(); // approval
    expect(screen.getByText("Archive cold emails?")).toBeInTheDocument(); // question
    expect(screen.getByText("Overnight outbound")).toBeInTheDocument(); // routine created
    expect(screen.getByText("18 KB")).toBeInTheDocument(); // file
    expect(screen.getByText("· Draft openers")).toBeInTheDocument(); // handoff
  });

  it("opens the reasoning when you click it", async () => {
    const { user } = renderUI(<MessageParts message={everyPart} isOwn={false} />);
    expect(screen.queryByText("Thinking it through.")).not.toBeInTheDocument();
    await user.click(screen.getByText("Thought for 3s"));
    expect(screen.getByText("Thinking it through.")).toBeInTheDocument();
  });

  it("collapses a question to the chosen answer", async () => {
    const message: Message = { ...everyPart, id: "m13", parts: [{ type: "question", question: "Archive cold emails?", options: ["Yes", "No"] }] };
    const { user, rerender } = renderUI(<MessageParts message={message} isOwn={false} />);
    await user.click(screen.getByRole("button", { name: "No" }));

    // The store now holds the answer; render the updated message like the thread would.
    rerender(<MessageParts message={{ ...message, parts: [{ ...message.parts[0], answered: "No" } as Message["parts"][0]] }} isOwn={false} />);
    expect(screen.queryByRole("button", { name: "Yes" })).not.toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();
  });
});
