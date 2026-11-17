import { afterEach, describe, expect, it } from "vitest";
import { markOnboardingDone, onboardingDone } from "./done-flag";

describe("the done flag", () => {
  afterEach(() => localStorage.clear());

  it("is remembered per organization", () => {
    expect(onboardingDone("o1")).toBe(false);
    markOnboardingDone("o1");
    expect(onboardingDone("o1")).toBe(true);
    expect(onboardingDone("o2")).toBe(false);
  });
});
