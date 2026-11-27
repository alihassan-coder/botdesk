import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Message, ToolCallPart } from "@/data/types";
import { renderUI } from "@/test/render";
import { MessageParts } from "./message-parts";

const withParts = (...parts: ToolCallPart[]): Message => ({
  id: "m_tools", threadId: "t_chief", author: { type: "bot", id: "b_chief" }, createdAt: "2026-11-27T09:00:00Z", parts,
});

const run = (patch: Partial<ToolCallPart>): ToolCallPart => ({
  type: "tool-call", toolExecutionId: "x1", tool: "computer.run", status: "succeeded", args: { command: "pnpm test --run", cwd: "/root/app" }, ...patch,
});

describe("A cloud computer's tool cards", () => {
  it("a command shows what it ran, its exit code and time, with the output behind a toggle", async () => {
    const { user } = renderUI(<MessageParts isOwn={false} message={withParts(run({ result: { exitCode: 0, output: "✓ 42 passed\nDone\n", seconds: 3.2, cwd: "/root/app" } }))} />);
    const card = screen.getByRole("group", { name: "Command" });
    expect(card).toHaveTextContent("$ pnpm test --run");
    expect(card).toHaveTextContent("in /root/app");
    expect(screen.getByText("exit 0")).not.toHaveClass("text-destructive");
    expect(screen.getByText("3.2 s")).toBeInTheDocument();
    expect(screen.queryByLabelText("Output")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Output · 2 lines" }));
    expect(screen.getByLabelText("Output")).toHaveTextContent("✓ 42 passed");
  });

  it("a failed command stands out, opens its output, and says when the output was cut", () => {
    // The API keeps the first and last 8 KB of long output, with its mark between them.
    const output = "Error: expected 2, got 3\n… 40960 bytes cut …\n    at sum.test.ts:4\n";
    renderUI(<MessageParts isOwn={false} message={withParts(run({ result: { exitCode: 1, output, seconds: 0.4 } }))} />);
    expect(screen.getByText("exit 1")).toHaveClass("text-destructive");
    expect(screen.getByLabelText("Output")).toHaveTextContent("Error: expected 2, got 3");
    expect(screen.getByText("Long output: only its first and last 8 KB were kept.")).toBeInTheDocument();
  });

  it("a read-only command while it runs, and one with no output", () => {
    renderUI(<MessageParts isOwn={false} message={withParts(
      run({ toolExecutionId: "x1", tool: "computer.inspect", status: "running", args: { command: "git status" } }),
      run({ toolExecutionId: "x2", tool: "computer.inspect", args: { command: "true" }, result: { exitCode: 0, output: "" } }),
    )} />);
    const [running, quiet] = screen.getAllByRole("group", { name: "Read-only command" });
    expect(running).toHaveTextContent("$ git status");
    expect(running).toHaveTextContent("running");
    expect(quiet).toHaveTextContent("No output");
  });

  it("a preview is a link card, saying who can open it", () => {
    renderUI(<MessageParts isOwn={false} message={withParts(
      { type: "tool-call", toolExecutionId: "x3", tool: "computer.preview", status: "succeeded", args: { port: 3000 }, result: { url: "https://web-ab3k.orgo.dev", port: 3000, access: "team" } },
    )} />);
    expect(screen.getByText("Preview of port 3000")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://web-ab3k.orgo.dev" })).toHaveAttribute("target", "_blank");
    expect(screen.getByText("Only people in your Orgo workspace can open it.")).toBeInTheDocument();
  });

  it("other computer tools, and a command without its arguments, stay a plain line", () => {
    renderUI(<MessageParts isOwn={false} message={withParts(
      { type: "tool-call", toolExecutionId: "x4", tool: "computer.start_app", status: "succeeded" },
      { type: "tool-call", toolExecutionId: "x5", tool: "computer.run", status: "failed", error: "Orgo says the account is out of credit." },
    )} />);
    expect(screen.getByText("Start app").parentElement).toHaveTextContent("Used Start app · done");
    expect(screen.getByText("Orgo says the account is out of credit.")).toBeInTheDocument();
  });
});
