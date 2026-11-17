import { describe, expect, it } from "vitest";
import { needsOnboarding } from "./onboarding";

const newOwner = { demo: false, botsLoading: false, botCount: 0, role: "owner" as const, done: false };

describe("needsOnboarding", () => {
  it("sends the owner of a brand-new organization (no bots yet) to setup", () => {
    expect(needsOnboarding(newOwner)).toBe(true);
  });

  it("leaves everyone else in the app", () => {
    expect(needsOnboarding({ ...newOwner, role: "admin" })).toBe(false);
    expect(needsOnboarding({ ...newOwner, role: "member" })).toBe(false);
    expect(needsOnboarding({ ...newOwner, botCount: 1 })).toBe(false);
    expect(needsOnboarding({ ...newOwner, done: true })).toBe(false);
    expect(needsOnboarding({ ...newOwner, demo: true })).toBe(false);
  });

  it("waits for the bots to load before deciding", () => {
    expect(needsOnboarding({ ...newOwner, botsLoading: true })).toBe(false);
  });
});
