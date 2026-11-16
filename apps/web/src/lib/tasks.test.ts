import { describe, expect, it } from "vitest";
import type { HandoffPart, Message } from "@/data/types";
import { isTaskOpen, newerTaskChange, plainPreview, taskPreview, withTaskChange, withTaskChangeIn } from "./tasks";

const card: HandoffPart = { type: "handoff", taskId: "t1", fromBotId: "b1", toBotId: "b2", task: "Draft openers", status: "working" };

describe("handoff cards", () => {
  it("queued and working are open; done, failed and cancelled are final", () => {
    expect(["queued", "working", "done", "failed", "cancelled"].map((s) => isTaskOpen(s as HandoffPart["status"]))).toEqual([true, true, false, false, false]);
  });

  it("a change moves the card on, and replaces its result fields", () => {
    expect(withTaskChange(card, { taskId: "t1", status: "done", resultMessageId: "m9", resultPreview: "Three drafts." })).toEqual({
      ...card, status: "done", resultMessageId: "m9", resultPreview: "Three drafts.",
    });
  });

  it("never moves a card backwards, and ignores another task's change", () => {
    expect(withTaskChange(card, { taskId: "t1", status: "queued" })).toBe(card);
    expect(withTaskChange(card, { taskId: "t2", status: "done" })).toBe(card);
  });

  it("changes the card in every message, and leaves other messages as they were", () => {
    const other: Message = { id: "m1", threadId: "x", author: { type: "bot", id: "b1" }, parts: [], createdAt: "" };
    const holder: Message = { ...other, id: "m2", parts: [{ type: "text", text: "On it." }, card] };
    const [a, b] = withTaskChangeIn([other, holder], { taskId: "t1", status: "failed", error: "Out of budget." });
    expect(a).toBe(other);
    expect(b.parts[1]).toMatchObject({ status: "failed", error: "Out of budget." });
  });

  it("keeps the newer of two changes", () => {
    const done = { taskId: "t1", status: "done" as const };
    expect(newerTaskChange(done, { taskId: "t1", status: "working" })).toBe(done);
    expect(newerTaskChange(undefined, done)).toBe(done);
  });

  it("makes a preview like the API: whitespace collapsed, 280 characters at most", () => {
    expect(taskPreview("  One\n\ntwo   three ")).toBe("One two three");
    expect(taskPreview("x".repeat(300))).toHaveLength(280);
  });

  it("shows a preview without bold and code marks (it's cut mid-Markdown)", () => {
    expect(plainPreview("- **Customers:** run `sso`")).toBe("- Customers: run sso");
  });
});
