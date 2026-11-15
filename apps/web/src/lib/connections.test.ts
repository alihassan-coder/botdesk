import { describe, expect, it } from "vitest";
import type { AccountConnection } from "@/data/types";
import { accessLabel, bindableConnections, callbackOutcome, ownerLabel, ownerOf } from "./connections";

const account = (patch: Partial<AccountConnection>): AccountConnection => ({
  id: "c1", connectorId: "gmail", ownerKind: "member", ownerUserId: "u1", ownerBotId: null, authType: "oauth2",
  accountLabel: "zara@example.com", scopes: [], status: "active", statusReason: null, createdAt: "2026-11-15T00:00:00Z", lastUsedAt: null,
  ...patch,
});

describe("connections", () => {
  it("names access levels, capitalising unknown ones", () => {
    expect(accessLabel("read")).toBe("Read only");
    expect(accessLabel("full")).toBe("Read, organise, draft and send");
    expect(accessLabel("admin")).toBe("Admin");
  });

  it("maps the callback's result and code to a message, unknown codes to the generic one", () => {
    expect(callbackOutcome("connected", null, "gmail")).toEqual({ ok: true, connectorId: "gmail" });
    expect(callbackOutcome("error", "denied", null)).toEqual({ ok: false, message: "You cancelled signing in, so nothing was connected." });
    expect(callbackOutcome("error", "expired", null)).toMatchObject({ message: expect.stringContaining("took too long") });
    expect(callbackOutcome("error", "<script>", null)).toMatchObject({ message: "Couldn't finish connecting the app. Try again." });
    expect(callbackOutcome(null, null, null)).toMatchObject({ ok: false });
  });

  it("says whose account it is", () => {
    const bots = (id: string) => (id === "b1" ? "Scout" : undefined);
    expect(ownerLabel(account({}), "u1", bots)).toBe("Just you");
    expect(ownerLabel(account({ ownerUserId: "u2" }), "u1", bots)).toBe("Another member");
    expect(ownerLabel(account({ ownerKind: "bot", ownerUserId: null, ownerBotId: "b1" }), "u1", bots)).toBe("Scout");
    expect(ownerLabel(account({ ownerKind: "org", ownerUserId: null }), "u1", bots)).toBe("Organization");
    expect(ownerOf(account({ ownerKind: "bot", ownerBotId: "b1" }))).toEqual({ kind: "bot", botId: "b1" });
  });

  it("offers a bot only active accounts that are yours, its own or the organization's", () => {
    const accounts = [
      account({ id: "mine" }),
      account({ id: "theirs", ownerUserId: "u2" }),
      account({ id: "scouts", ownerKind: "bot", ownerUserId: null, ownerBotId: "b1" }),
      account({ id: "other-bot", ownerKind: "bot", ownerUserId: null, ownerBotId: "b2" }),
      account({ id: "org", ownerKind: "org", ownerUserId: null }),
      account({ id: "broken", status: "needs_reconnect" }),
      account({ id: "slack", connectorId: "slack" }),
    ];
    expect(bindableConnections(accounts, "gmail", "b1", "u1").map((c) => c.id)).toEqual(["mine", "scouts", "org"]);
  });
});
