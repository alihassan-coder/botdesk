import { describe, expect, it } from "vitest";
import { formatBytes, formatCount, formatShortAgo, formatUsd, initialOf } from "./format";

const NOW = new Date("2026-11-12T12:00:00Z").getTime();
const minutesAgo = (m: number) => new Date(NOW - m * 60_000).toISOString();

describe("formatShortAgo", () => {
  it("says now for under a minute", () => {
    expect(formatShortAgo(minutesAgo(0.5), NOW)).toBe("now");
  });

  it("uses minutes, then hours", () => {
    expect(formatShortAgo(minutesAgo(5), NOW)).toBe("5m");
    expect(formatShortAgo(minutesAgo(180), NOW)).toBe("3h");
  });

  it("says Yesterday between one and two days", () => {
    expect(formatShortAgo(minutesAgo(60 * 30), NOW)).toBe("Yesterday");
  });

  it("uses a weekday within a week, then a date", () => {
    expect(formatShortAgo(minutesAgo(60 * 24 * 3), NOW)).toBe("Mon");
    expect(formatShortAgo(minutesAgo(60 * 24 * 10), NOW)).toBe("Nov 2");
  });

  it("never shows a negative time for clocks that are slightly ahead", () => {
    expect(formatShortAgo(new Date(NOW + 5_000).toISOString(), NOW)).toBe("now");
  });
});

describe("formatBytes", () => {
  it("picks a readable unit", () => {
    expect(formatBytes(980)).toBe("980 B");
    expect(formatBytes(18_204)).toBe("18 KB");
    expect(formatBytes(1_468_006)).toBe("1.4 MB");
  });
});

describe("formatUsd", () => {
  it("shows dollars with cents", () => {
    expect(formatUsd(31.4)).toBe("$31.40");
  });
});

describe("formatCount", () => {
  it("keeps small numbers and shortens big ones", () => {
    expect(formatCount(980)).toBe("980");
    expect(formatCount(12_400)).toBe("12.4k");
    expect(formatCount(2_000_000)).toBe("2M");
  });
});

describe("initialOf", () => {
  it("returns the first letter, uppercased", () => {
    expect(initialOf("inbox Manager")).toBe("I");
    expect(initialOf("  ")).toBe("?");
  });
});
