import { describe, expect, it } from "vitest";
import { strictestLevel } from "./security-level";

describe("strictestLevel", () => {
  it("picks the most careful level", () => {
    expect(strictestLevel("autonomous", "read-only")).toBe("read-only");
    expect(strictestLevel("ask-before-acting", "autonomous")).toBe("ask-before-acting");
    expect(strictestLevel("autonomous")).toBe("autonomous");
  });
});
