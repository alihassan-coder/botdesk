import { describe, expect, it } from "vitest";
import { formatShortcut, isApplePlatform } from "./platform";

describe("isApplePlatform", () => {
  it.each(["macOS", "MacIntel", "iPhone", "iPad", "iOS"])("is true for %s", (p) => {
    expect(isApplePlatform(p)).toBe(true);
  });
  it.each(["Windows", "Win32", "Linux x86_64", "Android", "Chrome OS", "", undefined, null])("is false for %s", (p) => {
    expect(isApplePlatform(p)).toBe(false);
  });
});

describe("formatShortcut", () => {
  it("uses ⌘ on Apple devices", () => expect(formatShortcut("k", true)).toBe("⌘K"));
  it("uses Ctrl+ elsewhere", () => expect(formatShortcut("b", false)).toBe("Ctrl+B"));
});
