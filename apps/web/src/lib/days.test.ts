import { describe, expect, it } from "vitest";
import { dayKey, dayLabel, startsADay } from "./days";

// 10:00 on Thursday, November 26, 2026 (UTC): 15:00 in Karachi, 02:00 in Los Angeles.
const NOW = Date.parse("2026-11-26T10:00:00Z");
const KARACHI = "Asia/Karachi";

describe("dayKey", () => {
  it("is the calendar day where you are, not in UTC", () => {
    // 20:00 UTC on the 25th is already 01:00 on the 26th in Karachi, still the 25th in Los Angeles.
    expect(dayKey("2026-11-25T20:00:00Z", KARACHI)).toBe("2026-11-26");
    expect(dayKey("2026-11-25T20:00:00Z", "America/Los_Angeles")).toBe("2026-11-25");
  });
});

describe("dayLabel", () => {
  it("says Today and Yesterday by calendar day, not by 24 hours", () => {
    expect(dayLabel("2026-11-26T04:00:00Z", NOW, KARACHI)).toBe("Today");
    expect(dayLabel("2026-11-25T20:00:00Z", NOW, KARACHI)).toBe("Today"); // 01:00 on the 26th there
    expect(dayLabel("2026-11-25T18:59:00Z", NOW, KARACHI)).toBe("Yesterday"); // 23:59 on the 25th
    expect(dayLabel("2026-11-24T19:30:00Z", NOW, KARACHI)).toBe("Yesterday"); // 00:30 on the 25th
  });

  it("gives the weekday within the last week, then the date", () => {
    expect(dayLabel("2026-11-24T08:00:00Z", NOW, KARACHI)).toBe("Tuesday");
    expect(dayLabel("2026-11-20T08:00:00Z", NOW, KARACHI)).toBe("Friday"); // six days back
    expect(dayLabel("2026-11-19T08:00:00Z", NOW, KARACHI)).toBe("November 19"); // a week back
    expect(dayLabel("2026-01-03T08:00:00Z", NOW, KARACHI)).toBe("January 3");
  });

  it("adds the year for another year", () => {
    expect(dayLabel("2025-12-31T08:00:00Z", NOW, KARACHI)).toBe("December 31, 2025");
  });

  it("calls a time a little ahead of this clock today, not tomorrow", () => {
    expect(dayLabel("2026-11-26T10:05:00Z", NOW, KARACHI)).toBe("Today");
  });

  it("works across a new year", () => {
    const newYear = Date.parse("2027-01-01T09:00:00Z");
    expect(dayLabel("2026-12-31T09:00:00Z", newYear, KARACHI)).toBe("Yesterday");
    expect(dayLabel("2026-12-28T09:00:00Z", newYear, KARACHI)).toBe("Monday");
  });
});

describe("startsADay", () => {
  const at = (createdAt: string) => ({ createdAt });

  it("marks the first message, and each one on a new day", () => {
    const messages = [
      at("2026-11-24T08:00:00Z"),
      at("2026-11-24T09:00:00Z"),
      at("2026-11-25T20:00:00Z"), // the 26th in Karachi, still the 25th in Los Angeles
      at("2026-11-26T09:00:00Z"), // the 26th in both
    ];
    expect(startsADay(messages, KARACHI)).toEqual([true, false, true, false]);
    expect(startsADay(messages, "America/Los_Angeles")).toEqual([true, false, true, true]);
  });

  it("is empty for no messages", () => {
    expect(startsADay([], KARACHI)).toEqual([]);
  });
});
