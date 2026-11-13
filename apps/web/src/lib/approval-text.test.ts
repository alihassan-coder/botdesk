import { describe, expect, it } from "vitest";
import { explainReason, expiryLabel, toolTitle } from "./approval-text";

describe("approval wording", () => {
  it("toolTitle drops the plugin and reads like a name", () => {
    expect(toolTitle("demo.send_email")).toBe("Send email");
    expect(toolTitle("current_time")).toBe("Current time");
  });

  it("explainReason turns the policy trace into a sentence", () => {
    expect(explainReason("level=Ask before acting · risk=external-send · tainted=no → ask")).toBe("Asked because the bot is set to “Ask before acting”.");
    expect(explainReason("level=Autonomous within limits · risk=external-send · tainted=yes → ask")).toMatch(/read outside content/);
    expect(explainReason("a rule we don't know")).toBe("a rule we don't know");
  });

  it("expiryLabel counts down in days, then hours", () => {
    const now = Date.parse("2026-11-12T12:00:00Z");
    expect(expiryLabel("2026-11-15T12:00:00Z", now)).toBe("Expires in 3 days");
    expect(expiryLabel("2026-11-13T13:00:00Z", now)).toBe("Expires in 1 day");
    expect(expiryLabel("2026-11-12T17:30:00Z", now)).toBe("Expires in 5h");
    expect(expiryLabel("2026-11-12T12:20:00Z", now)).toBe("Expires in under an hour");
    expect(expiryLabel("2026-11-12T11:00:00Z", now)).toBe("Past its expiry");
  });
});
