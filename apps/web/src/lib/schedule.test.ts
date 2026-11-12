import { describe, expect, it } from "vitest";
import { describeSchedule, formatTime } from "./schedule";

describe("formatTime", () => {
  it("drops :00 and uses AM/PM", () => {
    expect(formatTime("07:00")).toBe("7 AM");
    expect(formatTime("13:30")).toBe("1:30 PM");
  });

  it("handles midnight and noon", () => {
    expect(formatTime("00:00")).toBe("12 AM");
    expect(formatTime("12:05")).toBe("12:05 PM");
  });
});

describe("describeSchedule", () => {
  it("reads like a sentence", () => {
    expect(describeSchedule({ kind: "daily", time: "09:00" })).toBe("Every day at 9 AM");
    expect(describeSchedule({ kind: "weekdays", time: "07:00" })).toBe("Weekdays at 7 AM");
    expect(describeSchedule({ kind: "weekly", day: "Friday", time: "17:00" })).toBe("Every Friday at 5 PM");
    expect(describeSchedule({ kind: "monthly", time: "08:30" })).toBe("On the 1st of every month at 8:30 AM");
    expect(describeSchedule({ kind: "trigger", trigger: "new-email" })).toBe("When a new email arrives");
  });
});
