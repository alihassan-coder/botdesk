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

  it("the Send button works too, and trims extra spaces", async () => {
    const { user } = renderUI(<Composer thread={salesThread()} />);
    await user.type(screen.getByRole("textbox", { name: "Message Sales Outbound" }), "   Hello   ");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(lastText()).toBe("Hello");
  });
});
