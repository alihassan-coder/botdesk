import { describe, expect, it } from "vitest";
import { keyMeaning, scrollDelta, textPieces, toAddress, toPagePoint } from "./browser";

const page = { width: 1280, height: 800 };
const press = (key: string, mods: Partial<Record<"shiftKey" | "ctrlKey" | "metaKey" | "altKey", boolean>> = {}) =>
  keyMeaning({ key, shiftKey: false, ctrlKey: false, metaKey: false, altKey: false, ...mods });

describe("toPagePoint", () => {
  it("scales a click on the shown picture up to page pixels", () => {
    const shown = { left: 100, top: 50, width: 640, height: 400 };
    expect(toPagePoint(100, 50, shown, page)).toEqual({ x: 0, y: 0 });
    expect(toPagePoint(420, 250, shown, page)).toEqual({ x: 640, y: 400 });
    expect(toPagePoint(419.6, 249.9, shown, page)).toEqual({ x: 639, y: 399 });
  });

  it("keeps the point inside the page, even on the picture's very edge", () => {
    const shown = { left: 0, top: 0, width: 320, height: 200 };
    expect(toPagePoint(320, 200, shown, page)).toEqual({ x: 1279, y: 799 });
    expect(toPagePoint(-3, -3, shown, page)).toEqual({ x: 0, y: 0 });
  });
});

describe("keyMeaning", () => {
  it("types printable characters, the space included", () => {
    expect(press("a")).toEqual({ kind: "text", text: "a" });
    expect(press("A", { shiftKey: true })).toEqual({ kind: "text", text: "A" });
    expect(press(" ")).toEqual({ kind: "text", text: " " });
    expect(press("@", { ctrlKey: true, altKey: true })).toEqual({ kind: "text", text: "@" }); // AltGr
  });

  it("sends the special keys the API knows, Shift+Tab as one", () => {
    expect(press("Enter")).toEqual({ kind: "key", key: "Enter" });
    expect(press("Tab")).toEqual({ kind: "key", key: "Tab" });
    expect(press("Tab", { shiftKey: true })).toEqual({ kind: "key", key: "Shift+Tab" });
    expect(press("ArrowDown")).toEqual({ kind: "key", key: "ArrowDown" });
  });

  it("leaves shortcuts and keys it doesn't send to this browser", () => {
    expect(press("v", { ctrlKey: true })).toBeNull();
    expect(press("c", { metaKey: true })).toBeNull();
    expect(press("Shift", { shiftKey: true })).toBeNull();
    expect(press("F5")).toBeNull();
  });
});

describe("scrollDelta", () => {
  it("turns lines and pages into pixels, within ±3000", () => {
    expect(scrollDelta(120, 0)).toBe(120);
    expect(scrollDelta(3, 1)).toBe(120);
    expect(scrollDelta(-10, 2)).toBe(-3000);
  });
});

describe("textPieces and toAddress", () => {
  it("splits long text without breaking a character", () => {
    expect(textPieces("ab😀cd", 3)).toEqual(["ab😀", "cd"]);
  });

  it("adds https:// to an address typed without one", () => {
    expect(toAddress(" example.com/login ")).toBe("https://example.com/login");
    expect(toAddress("http://intranet.test")).toBe("http://intranet.test");
    expect(toAddress("   ")).toBe("");
  });
});
