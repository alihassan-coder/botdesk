import { describe, expect, it } from "vitest";
import { commandResult, computerKeyOf, computerSpecs, describeBotComputer, formatSeconds, isWorkspaceOnly, lineCount, previewResult } from "./computer";

const press = (key: string, mods: Partial<{ shiftKey: boolean; ctrlKey: boolean; metaKey: boolean; altKey: boolean }> = {}) =>
  computerKeyOf({ key, shiftKey: false, ctrlKey: false, metaKey: false, altKey: false, ...mods });

describe("computerKeyOf", () => {
  it("types characters, and sends the computer's own names for special keys", () => {
    expect(press("a")).toEqual({ kind: "text", text: "a" });
    expect(press(" ")).toEqual({ kind: "text", text: " " });
    expect(press("Backspace")).toEqual({ kind: "key", key: "BackSpace" });
    expect(press("ArrowUp")).toEqual({ kind: "key", key: "Up" });
    expect(press("PageDown")).toEqual({ kind: "key", key: "Page_Down" });
  });

  it("sends Ctrl+C, A and L to the computer, but leaves paste and other shortcuts here", () => {
    expect(press("c", { ctrlKey: true })).toEqual({ kind: "key", key: "ctrl+c" });
    expect(press("L", { ctrlKey: true, shiftKey: true })).toEqual({ kind: "key", key: "ctrl+l" });
    expect(press("v", { ctrlKey: true })).toBeNull();
    expect(press("r", { ctrlKey: true })).toBeNull();
    expect(press("c", { metaKey: true })).toBeNull();
    // AltGr types characters on Windows keyboards.
    expect(press("@", { ctrlKey: true, altKey: true })).toEqual({ kind: "text", text: "@" });
  });

  it("leaves Shift+Tab and keys the computer doesn't take to this browser", () => {
    expect(press("Tab", { shiftKey: true })).toBeNull();
    expect(press("Shift", { shiftKey: true })).toBeNull();
    expect(press("F5")).toBeNull();
  });
});

describe("commandResult", () => {
  it("reads a command's exit code, output, time and folder", () => {
    expect(commandResult({ exitCode: 1, output: "FAIL\n", seconds: 2.5, cwd: "/root/app" })).toEqual({
      exitCode: 1, output: "FAIL\n", seconds: 2.5, cwd: "/root/app", cut: false,
    });
    expect(commandResult({ exitCode: 0, output: "start\n… 40960 bytes cut …\nend" })?.cut).toBe(true);
    expect(commandResult({ exitCode: 0, output: "a…b", truncated: true })?.cut).toBe(true);
    expect(commandResult({ exitCode: 0, output: "nothing cut here …" })?.cut).toBe(false);
  });

  it("is nothing for a result that isn't a command's", () => {
    expect(commandResult(undefined)).toBeUndefined();
    expect(commandResult({ output: "x" })).toBeUndefined();
  });
});

describe("previewResult", () => {
  it("reads the URL, port and who can open it, and only takes web addresses", () => {
    expect(previewResult({ url: "https://web-ab3k.orgo.dev", port: 3000, access: "team" })).toEqual({ url: "https://web-ab3k.orgo.dev", port: 3000, access: "team" });
    expect(previewResult({ url: "javascript:alert(1)" })).toBeUndefined();
    expect(isWorkspaceOnly("team")).toBe(true);
    expect(isWorkspaceOnly("link")).toBe(false);
  });
});

describe("the computer's words", () => {
  it("says what a bot works on, how big its computer is, and how long a command took", () => {
    expect(describeBotComputer("browser")).toBe("Files and a browser");
    expect(describeBotComputer("cloud")).toBe("Files and a cloud computer");
    expect(computerSpecs({ status: "running", cpu: 2, ram: 8, region: "us-east", apps: [], previews: [] })).toBe("2 vCPU · 8 GB · us-east");
    expect(computerSpecs({ status: "none", apps: [], previews: [] })).toBe("");
    expect(formatSeconds(0.42)).toBe("0.4 s");
    expect(formatSeconds(12.3)).toBe("12 s");
    expect(formatSeconds(125)).toBe("2 min 5 s");
    expect(lineCount("")).toBe(0);
    expect(lineCount("a\nb\n")).toBe(2);
  });
});
