import { describe, expect, it } from "vitest";
import { describeCron, describeSchedule, formatTime, fromCron, isCronLine, toCron } from "./schedule";

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

describe("schedules as cron lines (routines on the API)", () => {
  it("turns each preset into a 5-field cron line", () => {
    expect(toCron({ kind: "daily", time: "09:00" })).toBe("0 9 * * *");
    expect(toCron({ kind: "weekdays", time: "07:30" })).toBe("30 7 * * 1-5");
    expect(toCron({ kind: "weekly", day: "Friday", time: "17:00" })).toBe("0 17 * * 5");
    expect(toCron({ kind: "weekly", day: "Sunday", time: "08:00" })).toBe("0 8 * * 0");
    expect(toCron({ kind: "hourly" })).toBe("0 * * * *");
    expect(toCron({ kind: "cron", cron: "  */15  8-18 * * 1-5 " })).toBe("*/15 8-18 * * 1-5");
  });

  it("reads a preset back from its cron line, so editing shows the same picker", () => {
    expect(fromCron("0 9 * * *")).toEqual({ kind: "daily", time: "09:00" });
    expect(fromCron("30 7 * * 1-5")).toEqual({ kind: "weekdays", time: "07:30" });
    expect(fromCron("0 17 * * 5")).toEqual({ kind: "weekly", day: "Friday", time: "17:00" });
    expect(fromCron("0 8 * * 7")).toEqual({ kind: "weekly", day: "Sunday", time: "08:00" });
    expect(fromCron("0 * * * *")).toEqual({ kind: "hourly" });
    expect(fromCron("*/15 8-18 * * 1-5")).toEqual({ kind: "cron", cron: "*/15 8-18 * * 1-5" });
  });

  it("describes any cron line in words, falling back to the line itself", () => {
    expect(describeCron("30 7 * * 1-5")).toBe("Weekdays at 7:30 AM");
    expect(describeCron("0 * * * *")).toBe("Every hour");
    expect(describeCron("*/15 8-18 * * 1-5")).toBe("Custom schedule: */15 8-18 * * 1-5");
  });

  it("knows a 5-field line from anything else", () => {
    expect(isCronLine("0 9 * * *")).toBe(true);
    expect(isCronLine("0 9 * *")).toBe(false);
    expect(isCronLine("every day")).toBe(false);
  });
});
