import { afterEach, describe, expect, it } from "vitest";
import { clearDraft, insertAtCaret, loadDraft, saveDraft, stepHistory } from "./drafts";

describe("drafts", () => {
  afterEach(() => localStorage.clear());

  it("keeps a chat's draft until it's cleared, and never keeps an empty one", () => {
    saveDraft("t1", "half a thought");
    saveDraft("t2", "another chat");
    expect(loadDraft("t1")).toBe("half a thought");
    expect(loadDraft("t2")).toBe("another chat");
    clearDraft("t1");
    expect(loadDraft("t1")).toBe("");
    saveDraft("t2", "   ");
    expect(localStorage.length).toBe(0);
  });
});

describe("stepHistory", () => {
  const sent = ["first", "second", "third"];

  it("Up starts at the newest and stops at the oldest", () => {
    expect(stepHistory(sent, null, "up")).toBe(2);
    expect(stepHistory(sent, 2, "up")).toBe(1);
    expect(stepHistory(sent, 0, "up")).toBe(0);
  });

  it("Down goes back toward your draft", () => {
    expect(stepHistory(sent, 1, "down")).toBe(2);
    expect(stepHistory(sent, 2, "down")).toBeNull();
    expect(stepHistory(sent, null, "down")).toBeNull();
  });

  it("with nothing sent there's nowhere to go", () => {
    expect(stepHistory([], null, "up")).toBeNull();
  });
});

describe("insertAtCaret", () => {
  it("adds spaces only where the words would touch", () => {
    expect(insertAtCaret("", 0, "hello")).toEqual({ text: "hello", caret: 5 });
    expect(insertAtCaret("Fix the bug", 11, "in the loader")).toEqual({ text: "Fix the bug in the loader", caret: 25 });
    expect(insertAtCaret("Fix bug", 3, "the")).toEqual({ text: "Fix the bug", caret: 7 });
    expect(insertAtCaret("Fix ", 4, "it")).toEqual({ text: "Fix it", caret: 6 });
  });
});
