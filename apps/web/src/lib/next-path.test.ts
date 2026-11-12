import { describe, expect, it } from "vitest";
import { safeNextPath } from "./next-path";

describe("safeNextPath", () => {
  it("returns the page you were going to", () => {
    expect(safeNextPath("?next=%2Fsettings%2Fusage%3Ftab%3D1")).toBe("/settings/usage?tab=1");
  });

  it("goes home when there's no next page", () => {
    expect(safeNextPath("")).toBe("/");
  });

  it("never leaves the site", () => {
    expect(safeNextPath("?next=https://evil.com")).toBe("/");
    expect(safeNextPath("?next=//evil.com")).toBe("/");
    expect(safeNextPath("?next=/%5Cevil.com")).toBe("/");
  });
});
