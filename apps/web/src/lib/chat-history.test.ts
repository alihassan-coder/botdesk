import { describe, expect, it } from "vitest";
import { deletesMore, retentionFromValue, retentionLabel, retentionValue } from "./chat-history";

describe("deletesMore", () => {
  it("is true for any limit after Never, and for a shorter one", () => {
    expect(deletesMore(null, 365)).toBe(true);
    expect(deletesMore(90, 30)).toBe(true);
  });

  it("is false for a longer limit, the same one, or Never", () => {
    expect(deletesMore(30, 90)).toBe(false);
    expect(deletesMore(90, 90)).toBe(false);
    expect(deletesMore(30, null)).toBe(false);
    expect(deletesMore(null, null)).toBe(false);
  });
});

describe("retention labels and values", () => {
  it("names each choice", () => {
    expect(retentionLabel(null)).toBe("Never");
    expect(retentionLabel(180)).toBe("180 days");
    expect(retentionLabel(365)).toBe("1 year");
  });

  it("goes to a Select's value and back", () => {
    expect(retentionValue(null)).toBe("never");
    expect(retentionValue(90)).toBe("90");
    expect(retentionFromValue("90")).toBe(90);
    expect(retentionFromValue("never")).toBeNull();
  });
});
