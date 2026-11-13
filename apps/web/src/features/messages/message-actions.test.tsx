import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Message } from "@/data/types";
import { renderUI } from "@/test/render";
import { MessageActions, messageText } from "./message-actions";

const reply: Message = {
  id: "m_1",
  threadId: "t_1",
  author: { type: "bot", id: "b_chief" },
  createdAt: "2026-11-13T09:30:00Z",
  parts: [
    { type: "text", text: "**Done.** Sent 2 emails." },
    { type: "tool-call", toolExecutionId: "x1", tool: "demo.send_email", status: "succeeded" },
    { type: "text", text: "  Anything else?  " },
  ],
};

describe("messageText", () => {
  it("joins the text parts as written, markdown included", () => {
    expect(messageText(reply)).toBe("**Done.** Sent 2 emails.\n\nAnything else?");
  });
});

describe("MessageActions", () => {
  it("copies the message and says so", async () => {
    const { user } = renderUI(<MessageActions message={reply} isOwn={false} showTime />);
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();

    await user.click(screen.getByRole("button", { name: "Copy message" }));

    expect(writeText).toHaveBeenCalledWith("**Done.** Sent 2 emails.\n\nAnything else?");
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("waits until the reply has finished", () => {
    renderUI(<MessageActions message={{ ...reply, status: "streaming" }} isOwn={false} showTime />);
    expect(screen.queryByRole("button", { name: "Copy message" })).not.toBeInTheDocument();
  });

  it("shows nothing for a message without words", () => {
    renderUI(<MessageActions message={{ ...reply, parts: [reply.parts[1]] }} isOwn={false} showTime />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
