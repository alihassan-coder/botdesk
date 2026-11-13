import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { actions } from "@/data/store";
import type { Approval } from "@/data/types";
import { renderUI } from "@/test/render";
import { ApprovalEditor } from "./approval-editor";

const approval: Approval = {
  id: "a_9", botId: "b_inbox", threadId: "t_inbox", riskClass: "spend", status: "pending",
  title: "Pay an invoice", summary: "Pays Globex", preview: [], requestedAt: "2026-11-12T09:00:00Z",
  args: { to: "billing@globex.com", amount: 120, rush: false, method: "card", note: "" },
  argsSchema: {
    type: "object",
    properties: {
      to: { type: "string", title: "To", format: "email" },
      amount: { type: "integer", title: "Amount", minimum: 1 },
      rush: { type: "boolean", title: "Rush" },
      method: { type: "string", title: "Method", enum: ["card", "transfer"] },
      note: { type: "string", title: "Note", maxLength: 2000 },
    },
    required: ["to", "amount", "method"],
  },
};

afterEach(() => vi.restoreAllMocks());

function renderEditor() {
  const onClose = vi.fn();
  const decide = vi.spyOn(actions, "decideApproval");
  return { onClose, decide, ...renderUI(<ApprovalEditor approval={approval} onClose={onClose} />) };
}

describe("ApprovalEditor", () => {
  it("builds the right input for each argument, filled in from what the bot asked", () => {
    renderEditor();
    expect(screen.getByRole("textbox", { name: "To" })).toHaveValue("billing@globex.com");
    expect(screen.getByRole("spinbutton", { name: "Amount" })).toHaveValue(120);
    expect(screen.getByRole("checkbox", { name: "Rush" })).not.toBeChecked();
    expect(screen.getByRole("combobox", { name: "Method" })).toHaveValue("card");
    // A long allowed length means a body of text.
    expect(screen.getByRole("textbox", { name: /Note/ }).tagName).toBe("TEXTAREA");
  });

  it("sends the edited arguments with their types", async () => {
    const { user, decide, onClose } = renderEditor();
    decide.mockResolvedValue({ ok: true });
    const amount = screen.getByRole("spinbutton", { name: "Amount" });
    await user.clear(amount);
    await user.type(amount, "95");
    await user.click(screen.getByRole("checkbox", { name: "Rush" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Method" }), "transfer");
    await user.click(screen.getByRole("button", { name: "Approve edited version" }));

    expect(decide).toHaveBeenCalledWith("a_9", "approve", { to: "billing@globex.com", amount: 95, rush: true, method: "transfer", note: "" });
    expect(onClose).toHaveBeenCalled();
  });

  it("checks the fields before sending anything", async () => {
    const { user, decide } = renderEditor();
    await user.clear(screen.getByRole("textbox", { name: "To" }));
    await user.type(screen.getByRole("textbox", { name: "To" }), "billing");
    await user.clear(screen.getByRole("spinbutton", { name: "Amount" }));
    await user.click(screen.getByRole("button", { name: "Approve edited version" }));

    expect(screen.getByText("Enter an email address, like sara@acme.dev.")).toBeInTheDocument();
    expect(screen.getByText("Fill this in.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "To" })).toHaveAttribute("aria-invalid", "true");
    expect(decide).not.toHaveBeenCalled();
  });

  it("shows the API's field errors when the edit doesn't fit (400), and stays open", async () => {
    const { user, decide, onClose } = renderEditor();
    decide.mockResolvedValue({ ok: false, reason: "invalid", error: "Those changes don't fit this action: amount: Input should be less than 100" });
    await user.click(screen.getByRole("button", { name: "Approve edited version" }));

    expect(await screen.findByText("Input should be less than 100.")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("leaves it to the card when someone else decided first (409): it says who", async () => {
    const { user, decide, onClose } = renderEditor();
    decide.mockResolvedValue({ ok: false, reason: "conflict", status: "approved", error: "This approval was already decided." });
    await user.click(screen.getByRole("button", { name: "Approve edited version" }));
    await vi.waitFor(() => expect(decide).toHaveBeenCalled());
    expect(onClose).not.toHaveBeenCalled();
  });

  it("any other failure keeps the form open with your changes", async () => {
    const { user, decide, onClose } = renderEditor();
    decide.mockResolvedValue({ ok: false, status: "pending", error: "This tool isn't available any more." });
    const amount = screen.getByRole("spinbutton", { name: "Amount" });
    await user.clear(amount);
    await user.type(amount, "95");
    await user.click(screen.getByRole("button", { name: "Approve edited version" }));
    await vi.waitFor(() => expect(decide).toHaveBeenCalled());
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("spinbutton", { name: "Amount" })).toHaveValue(95);
  });

  it("opens with the first field focused", () => {
    renderEditor();
    expect(screen.getByRole("textbox", { name: "To" })).toHaveFocus();
  });
});
