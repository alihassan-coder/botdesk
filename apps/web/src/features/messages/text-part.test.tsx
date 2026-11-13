import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderUI } from "@/test/render";
import { TextPart } from "./text-part";

const REPLY = [
  "## Plan",
  "Here is **what I did** for @sales:",
  "",
  "- Sorted the inbox",
  "- [x] Drafted replies",
  "",
  "Email sara@acme.dev with `send_email`, see [the doc](https://example.com/doc).",
  "",
  "```bash",
  "pnpm test",
  "```",
  "",
  "| Bot | Spent |",
  "| --- | ----: |",
  "| Chief | $4 |",
  "",
  "<b>raw html</b> ![chart](https://tracker.example/c.png)",
].join("\n");

describe("TextPart", () => {
  it("formats a bot's reply as markdown", () => {
    renderUI(<TextPart part={{ type: "text", text: REPLY }} isOwn={false} isBot />);

    expect(screen.getByRole("heading", { name: "Plan" })).toBeInTheDocument();
    expect(screen.getByText("what I did").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("checkbox")).toBeChecked();
    expect(screen.getByText("send_email").tagName).toBe("CODE");
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("$4")).toBeInTheDocument();
  });

  it("opens links in a new tab and shows images as links", () => {
    renderUI(<TextPart part={{ type: "text", text: REPLY }} isOwn={false} isBot />);

    const link = screen.getByRole("link", { name: "the doc" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getByRole("link", { name: "chart" })).toHaveAttribute("href", "https://tracker.example/c.png");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("never renders raw HTML or unsafe links", () => {
    renderUI(<TextPart part={{ type: "text", text: "<b>raw</b> [click](javascript:alert(1))" }} isOwn={false} isBot />);

    expect(screen.queryByText("raw", { selector: "b" })).not.toBeInTheDocument();
    expect(screen.getByText("click").closest("a")?.getAttribute("href") ?? "").not.toContain("javascript");
  });

  it("shows a code block with its language and a copy button", () => {
    renderUI(<TextPart part={{ type: "text", text: REPLY }} isOwn={false} isBot />);

    expect(screen.getByText("bash")).toBeInTheDocument();
    expect(screen.getByText("pnpm test")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy code" })).toBeInTheDocument();
  });

  it("colours code once its language loads", async () => {
    const { container } = renderUI(<TextPart part={{ type: "text", text: "```bash\npnpm test\n```" }} isOwn={false} isBot />);

    await waitFor(() => expect(container.querySelector("[data-slot=code-block-line] [class*=shiki]")).not.toBeNull(), { timeout: 5000 });
    expect(screen.getByRole("button", { name: "Copy code" })).toBeInTheDocument();
  });

  it("colours @handles but not the @ in an email address", () => {
    renderUI(<TextPart part={{ type: "text", text: REPLY }} isOwn={false} isBot />);

    expect(screen.getByText("@sales")).toHaveClass("text-brand");
    expect(screen.queryByText("@acme")).not.toBeInTheDocument();
  });

  it("shows a person's message as typed, without markdown", () => {
    renderUI(<TextPart part={{ type: "text", text: "**not bold** ask @sales, mail sara@acme.dev" }} isOwn isBot={false} />);

    expect(screen.getByText(/\*\*not bold\*\*/)).toBeInTheDocument();
    expect(screen.getByText("@sales")).toHaveClass("font-semibold");
    expect(screen.queryByText("@acme")).not.toBeInTheDocument();
  });
});
