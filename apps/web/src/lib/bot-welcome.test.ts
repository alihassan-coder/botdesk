import { describe, expect, it } from "vitest";
import { botWelcome } from "./bot-welcome";

describe("botWelcome", () => {
  it("introduces the bot with its description, or its role when it has none", () => {
    expect(botWelcome({ name: "Chief", role: "Chief of staff", description: "Plans the work and keeps you posted." }))
      .toBe("Hi! I'm Chief. Plans the work and keeps you posted. What should I work on first?");
    expect(botWelcome({ name: "Scout", role: "Research", description: "" })).toBe("Hi! I'm Scout. Research. What should I work on first?");
    expect(botWelcome({ name: "Blank", role: "", description: "" })).toBe("Hi! I'm Blank. What should I work on first?");
  });
});
