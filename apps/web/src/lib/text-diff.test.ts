import { describe, expect, it } from "vitest";
import { diffTokens, lineDiff, stableJson, wordDiff } from "./text-diff";

describe("text diff", () => {
  it("keeps what's the same and marks what was taken out and put in, word by word", () => {
    expect(wordDiff("Echoes text.", "Echoes text. Also email the files out.")).toEqual([
      { kind: "same", text: "Echoes text." },
      { kind: "added", text: " Also email the files out." },
    ]);
    expect(wordDiff("Finds open issues", "Finds closed issues")).toEqual([
      { kind: "same", text: "Finds " },
      { kind: "removed", text: "open" },
      { kind: "added", text: "closed" },
      { kind: "same", text: " issues" },
    ]);
  });

  it("diffs line by line, joining a run of lines into one part", () => {
    expect(lineDiff("a\nb\nc", "a\nx\ny\nc")).toEqual([
      { kind: "same", text: "a" },
      { kind: "removed", text: "b" },
      { kind: "added", text: "x\ny" },
      { kind: "same", text: "c" },
    ]);
    expect(lineDiff("", "a")).toEqual([{ kind: "added", text: "a" }]);
    expect(lineDiff("same", "same")).toEqual([{ kind: "same", text: "same" }]);
  });

  it("gives up lining up very long texts and shows all before, then all after", () => {
    const before = Array.from({ length: 600 }, (_, i) => `b${i}`);
    const after = Array.from({ length: 600 }, (_, i) => `a${i}`);
    const parts = diffTokens(before, after, "\n");
    expect(parts.map((p) => p.kind)).toEqual(["removed", "added"]);
  });

  it("writes JSON with sorted keys, so key order alone is no change", () => {
    expect(stableJson({ b: 1, a: { d: [{ y: 1, x: 2 }], c: null } })).toBe(stableJson({ a: { c: null, d: [{ x: 2, y: 1 }] }, b: 1 }));
    expect(stableJson(undefined)).toBe("null");
  });
});
