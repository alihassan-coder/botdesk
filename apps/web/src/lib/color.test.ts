import { describe, expect, it } from "vitest";
import { isHexColor, readableTextOn } from "./color";

describe("readableTextOn", () => {
  it("puts white text on dark colours", () => {
    expect(readableTextOn("#3b30ff")).toBe("#ffffff");
    expect(readableTextOn("#000000")).toBe("#ffffff");
  });

  it("puts black text on light colours", () => {
    expect(readableTextOn("#ffd60a")).toBe("#000000");
    expect(readableTextOn("#ffffff")).toBe("#000000");
  });

  it("falls back to white for anything that isn't a colour", () => {
    expect(readableTextOn("nope")).toBe("#ffffff");
  });
});

describe("isHexColor", () => {
  it("accepts six-digit hex only", () => {
    expect(isHexColor("#3B30FF")).toBe(true);
    expect(isHexColor("#fff")).toBe(false);
    expect(isHexColor("3b30ff")).toBe(false);
  });
});
