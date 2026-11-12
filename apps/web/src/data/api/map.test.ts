import { describe, expect, it } from "vitest";
import { toOrg, toUser } from "./map";

describe("API → web shapes", () => {
  it("a user gets the role they hold in the org and shows as online", () => {
    expect(toUser({ id: "u1", name: "Zara", email: "zara@example.com", handle: "zara" }, "admin")).toEqual({
      id: "u1", name: "Zara", email: "zara@example.com", handle: "zara", role: "admin", presence: "online",
    });
  });

  it("an org drops the viewer's role, which belongs to the user", () => {
    expect(toOrg({ id: "o1", name: "Acme", slug: "acme", plan: "free", role: "owner" })).toEqual({ id: "o1", name: "Acme", slug: "acme", plan: "free" });
  });
});
