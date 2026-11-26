import { afterEach, describe, expect, it, vi } from "vitest";
import { getStoreSnapshot as state } from "@/data/store";
import { startsADay } from "@/lib/days";
import { renderUI } from "@/test/render";
import { DayDivider } from "./day-divider";
import { MessageList } from "./message-list";

// On this device's clock: the labels are calendar days where you are.
const at = (day: number, hour: number) => new Date(2026, 10, day, hour, 0).toISOString();

describe("DayDivider", () => {
  afterEach(() => vi.useRealTimers());

  it("says Today, Yesterday, the weekday within a week, then the date", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 10, 26, 15, 0)); // Thursday, November 26, 3 PM
    const { container } = renderUI(
      <>
        <DayDivider at={at(26, 9)} />
        <DayDivider at={at(25, 23)} />
        <DayDivider at={at(23, 8)} />
        <DayDivider at={at(12, 8)} />
      </>,
    );
    const labels = [...container.querySelectorAll("time")].map((t) => [t.textContent, t.getAttribute("datetime")]);
    expect(labels).toEqual([
      ["Today", "2026-11-26"],
      ["Yesterday", "2026-11-25"],
      ["Monday", "2026-11-23"],
      ["November 12", "2026-11-12"],
    ]);
  });
});

describe("MessageList's day dividers", () => {
  it("puts one above the first message of each day, inside that message's item", () => {
    const thread = state().threads.find((t) => t.id === "t_chief")!;
    const messages = state().messages.filter((m) => m.threadId === thread.id);
    const { container } = renderUI(<MessageList thread={thread} />);

    const items = [...container.querySelectorAll<HTMLElement>("[data-slot=message-scroller-item]")];
    const withDivider = items.filter((item) => item.querySelector(":scope > div > time"));
    expect(withDivider.map((item) => item.dataset.messageId)).toEqual(
      messages.filter((_, i) => startsADay(messages)[i]).map((m) => m.id),
    );
    // The scroller keeps your place when older messages load by watching which item comes first,
    // so a divider must never be an item of its own.
    const content = container.querySelector("[data-slot=message-scroller-content]")!;
    expect((content.firstElementChild as HTMLElement).dataset.messageId).toBe(messages[0].id);
  });
});
