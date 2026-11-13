import { describe, expect, it } from "vitest";
import { budgetOrder, budgetUse } from "./budget";

describe("budgetUse", () => {
  it("treats 0 or no budget as no limit", () => {
    expect(budgetUse(500, 0)).toEqual({ level: "none", percent: 0 });
    expect(budgetUse(5, undefined)).toEqual({ level: "none", percent: 0 });
  });

  it("is near from 80% used and reached at 100%", () => {
    expect(budgetUse(31.4, 80)).toMatchObject({ level: "ok" });
    expect(budgetUse(32, 40)).toEqual({ level: "near", percent: 80 });
    expect(budgetUse(40, 40)).toEqual({ level: "reached", percent: 100 });
  });

  it("caps the bar at 100% when spend went past the budget", () => {
    expect(budgetUse(50, 40)).toEqual({ level: "reached", percent: 100 });
  });
});

describe("budgetOrder", () => {
  it("puts the closest to its limit first and no-limit bots last", () => {
    const bots = [{ s: 1, b: 0 }, { s: 30, b: 40 }, { s: 5, b: 50 }];
    const sorted = [...bots].sort((x, y) => budgetOrder(y.s, y.b) - budgetOrder(x.s, x.b));
    expect(sorted.map((x) => x.b)).toEqual([40, 50, 0]);
  });
});
