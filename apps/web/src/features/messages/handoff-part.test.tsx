import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { HandoffPart as HandoffPartData, TaskStatus } from "@/data/types";
import { renderUI } from "@/test/render";
import { HandoffPart } from "./handoff-part";

const part = (status: TaskStatus, patch: Partial<HandoffPartData> = {}): HandoffPartData => ({
  type: "handoff", taskId: "k1", fromBotId: "b_chief", toBotId: "b_sales", task: "Draft three launch emails", status, ...patch,
});
const card = () => screen.getByRole("article", { name: "Chief handed a task to Sales Outbound" });

describe("HandoffPart", () => {
  it("shows who handed what to whom, as the card's heading", () => {
    renderUI(<HandoffPart part={part("queued")} />);
    expect(screen.getByRole("heading", { level: 3, name: "Chief handed a task to Sales Outbound" })).toBeInTheDocument();
    expect(within(card()).getByText("@sales")).toBeInTheDocument();
    expect(within(card()).getByText("Draft three launch emails")).toBeInTheDocument();
  });

  it.each([
    ["queued", "Queued"],
    ["working", "Working…"],
    ["done", "Done"],
    ["failed", "Failed"],
    ["cancelled", "Cancelled"],
  ] as const)("a %s task says %s, in a polite live region", (status, label) => {
    renderUI(<HandoffPart part={part(status)} />);
    const live = card().querySelector("[aria-live=polite]")!;
    expect(live).toHaveTextContent(`Sales Outbound's task: ${label}`);
  });

  it("while working, a quiet dot shows; it only moves when motion is welcome", () => {
    renderUI(<HandoffPart part={part("working")} />);
    expect(card().querySelector("[data-working-dot]")).toHaveClass("motion-safe:animate-pulse");
  });

  it("a status change replaces the badge, and announces it", () => {
    const { rerender } = renderUI(<HandoffPart part={part("working")} />);
    rerender(<HandoffPart part={part("done", { resultPreview: "Three drafts are ready." })} />);
    expect(card().querySelector("[aria-live=polite]")).toHaveTextContent("Sales Outbound's task: Done");
  });

  it("done: the result preview folds open, and View reply goes to the reply", async () => {
    const reply = document.createElement("div");
    reply.id = "message-m7";
    reply.tabIndex = -1;
    reply.scrollIntoView = vi.fn();
    document.body.append(reply);

    const { user } = renderUI(<HandoffPart part={part("done", { resultPreview: "Three drafts are ready.", resultMessageId: "m7" })} />);
    expect(screen.queryByText("Three drafts are ready.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show result" }));
    expect(screen.getByText("Three drafts are ready.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "View reply" }));
    expect(reply.scrollIntoView).toHaveBeenCalled();
    expect(reply).toHaveFocus();
    reply.remove();
  });

  it("failed: says why; out of budget offers to raise it", () => {
    renderUI(<HandoffPart part={part("failed", { error: "Sales Outbound reached its $60 monthly budget.", errorCode: "budget" })} />);
    expect(within(card()).getByText("Sales Outbound reached its $60 monthly budget.")).toBeInTheDocument();
    expect(within(card()).getByRole("link", { name: "Usage & budgets" })).toHaveAttribute("href", "/settings/usage");
  });

  it("cancelled: says why, with no result", () => {
    renderUI(<HandoffPart part={part("cancelled", { error: "Cancelled: Chief stopped before it finished." })} />);
    expect(within(card()).getByText("Cancelled: Chief stopped before it finished.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show result" })).not.toBeInTheDocument();
  });
});
