import { describe, expect, it } from "vitest";
import { inviteTokenFromNext, safeNextPath } from "./next-path";

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
    // Browsers drop tabs and newlines from a URL, so this one would become "//evil.com".
    expect(safeNextPath("?next=/%09/evil.com")).toBe("/");
  });
});

describe("inviteTokenFromNext", () => {
  it("finds the invite token when sign-up came from an invite link", () => {
    expect(inviteTokenFromNext("/invite/abc_DEF-123")).toBe("abc_DEF-123");
  });

  it("is null for any other page, or none", () => {
    expect(inviteTokenFromNext(undefined)).toBeNull();
    expect(inviteTokenFromNext("/settings")).toBeNull();
    expect(inviteTokenFromNext("/invite/")).toBeNull();
    expect(inviteTokenFromNext("/invite/a/b")).toBeNull();
  });
});
