import { describe, expect, it } from "vitest";
import { bestVoice, speakableText, speechChunks } from "./speech";

describe("speakableText", () => {
  it("reads markdown as words: no symbols, links by their words, code blocks named", () => {
    const markdown = [
      "## Fixed it",
      "I found the **cause**: the loader returns the whole file.",
      "",
      "- Changed `lib/tasks.ts`",
      "- See [the pull request](https://github.com/acme/app/pull/2)",
      "",
      "```ts",
      "return JSON.parse(json).tasks;",
      "```",
      "Details at https://example.com/x",
    ].join("\n");
    expect(speakableText(markdown)).toBe(
      "Fixed it. I found the cause: the loader returns the whole file. Changed lib/tasks.ts. See the pull request. Code block. Details at a link.",
    );
  });

  it("reads a table's cells without the pipes or the dashes", () => {
    const table = "| Task | Done |\n|---|---|\n| README | yes |";
    expect(speakableText(table)).toBe("Task, Done. README, yes.");
  });
});

describe("speechChunks", () => {
  it("groups sentences into pieces under the limit", () => {
    expect(speechChunks("One. Two! Three?", 9)).toEqual(["One. Two!", "Three?"]);
    expect(speechChunks("One. Two. Three.", 100)).toEqual(["One. Two. Three."]);
  });

  it("cuts a sentence longer than the limit at a space", () => {
    const chunks = speechChunks("alpha beta gamma delta epsilon zeta.", 12);
    expect(chunks.every((chunk) => chunk.length <= 12)).toBe(true);
    expect(chunks.join(" ")).toBe("alpha beta gamma delta epsilon zeta.");
  });

  it("keeps text without a full stop", () => {
    expect(speechChunks("no stop at the end")).toEqual(["no stop at the end"]);
  });
});

describe("bestVoice", () => {
  const voice = (name: string, lang: string, isDefault = false) => ({ name, lang, default: isDefault }) as SpeechSynthesisVoice;

  it("prefers a natural voice in the page's language", () => {
    const voices = [voice("Microsoft David", "en-US", true), voice("Microsoft Aria Online (Natural)", "en-US"), voice("Google français", "fr-FR")];
    expect(bestVoice(voices, "en-US")?.name).toBe("Microsoft Aria Online (Natural)");
  });

  it("falls back to any voice when none speaks the language", () => {
    expect(bestVoice([voice("Google français", "fr-FR")], "ur-PK")?.name).toBe("Google français");
    expect(bestVoice([], "en")).toBeUndefined();
  });
});
