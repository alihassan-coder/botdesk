import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getStoreSnapshot } from "@/data/store";
import { renderUI } from "@/test/render";
import { Composer } from "./composer";

const salesThread = () => getStoreSnapshot().threads.find((t) => t.id === "t_sales")!;
const lastText = () => {
  const last = getStoreSnapshot().messages.filter((m) => m.threadId === "t_sales").at(-1)!;
  return last.parts[0].type === "text" ? last.parts[0].text : null;
};

describe("Composer", () => {
  it("says who you're messaging", () => {
    renderUI(<Composer thread={salesThread()} />);
    expect(screen.getByPlaceholderText("Message Sales Outbound")).toBeInTheDocument();
  });

  it("can't send an empty message", () => {
    renderUI(<Composer thread={salesThread()} />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("Enter sends the message and clears the box", async () => {
    const { user } = renderUI(<Composer thread={salesThread()} />);
    const box = screen.getByRole("textbox", { name: "Message Sales Outbound" });

    await user.type(box, "Pause tonight's run{Enter}");

    expect(lastText()).toBe("Pause tonight's run");
    expect(box).toHaveValue("");
  });

  it("Shift+Enter adds a new line instead of sending", async () => {
    const { user } = renderUI(<Composer thread={salesThread()} />);
    const box = screen.getByRole("textbox", { name: "Message Sales Outbound" });
    const before = getStoreSnapshot().messages.length;

    await user.type(box, "Line one{Shift>}{Enter}{/Shift}Line two");

    expect(box).toHaveValue("Line one\nLine two");
    expect(getStoreSnapshot().messages.length).toBe(before);
  });

  describe("@mention suggestions", () => {
    const launchCrew = () => getStoreSnapshot().threads.find((t) => t.id === "t_launch")!;
    const box = () => screen.getByRole("textbox", { name: "Message Launch crew" });

    it("typing @ lists the bots and people in the chat, not you", async () => {
      const { user } = renderUI(<Composer thread={launchCrew()} />);
      await user.type(box(), "@");
      const names = screen.getAllByRole("option").map((o) => o.textContent);
      expect(names.some((n) => n?.includes("@chief"))).toBe(true);
      expect(names.some((n) => n?.includes("@sara"))).toBe(true);
      expect(names.some((n) => n?.includes("@ali"))).toBe(false);
      // Bots that aren't in this group aren't offered.
      expect(names.some((n) => n?.includes("@inbox"))).toBe(false);
    });

    it("in a DM, offers the DM's bot first, then every other bot, which joins as a guest", async () => {
      const chief = getStoreSnapshot().threads.find((t) => t.id === "t_chief")!;
      const { user } = renderUI(<Composer thread={chief} />);
      await user.type(screen.getByRole("textbox", { name: "Message Chief" }), "@");

      const options = screen.getAllByRole("option").map((o) => o.textContent ?? "");
      expect(options).toHaveLength(getStoreSnapshot().bots.length);
      expect(options[0]).toContain("@chief");
      expect(options[0]).not.toContain("Joins as a guest");
      expect(options.find((o) => o.includes("@inbox"))).toContain("Joins as a guest");
      expect(options.some((o) => o.includes("Teammate"))).toBe(false);
    });

    it("filters as you type, and Enter picks instead of sending", async () => {
      const { user } = renderUI(<Composer thread={launchCrew()} />);
      const before = getStoreSnapshot().messages.length;
      await user.type(box(), "ask @bu");
      expect(screen.getAllByRole("option")).toHaveLength(1);
      await user.keyboard("{Enter}");
      expect(box()).toHaveValue("ask @bugs ");
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
      expect(getStoreSnapshot().messages.length).toBe(before);
    });

    it("arrow keys move the highlight; clicking picks", async () => {
      const { user } = renderUI(<Composer thread={launchCrew()} />);
      await user.type(box(), "@");
      const first = screen.getAllByRole("option")[0];
      expect(first).toHaveAttribute("aria-selected", "true");
      await user.keyboard("{ArrowDown}");
      expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
      await user.click(screen.getAllByRole("option")[0]);
      expect((box() as HTMLTextAreaElement).value).toMatch(/^@[a-z0-9_-]+ $/);
    });

    it("Escape closes the list, and an email address never opens it", async () => {
      const { user } = renderUI(<Composer thread={launchCrew()} />);
      await user.type(box(), "@");
      await user.keyboard("{Escape}");
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
      await user.clear(box());
      await user.type(box(), "mail sara@ac");
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    });
  });

  it("the Send button works too, and trims extra spaces", async () => {
    const { user } = renderUI(<Composer thread={salesThread()} />);
    await user.type(screen.getByRole("textbox", { name: "Message Sales Outbound" }), "   Hello   ");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(lastText()).toBe("Hello");
  });
});
