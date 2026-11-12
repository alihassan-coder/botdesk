import { describe, expect, it } from "vitest";
import { canChangeRole, rolesYouCanGive } from "./roles";

describe("roles", () => {
  it("only owners can give the owner role", () => {
    expect(rolesYouCanGive("owner").map((r) => r.value)).toEqual(["owner", "admin", "member"]);
    expect(rolesYouCanGive("admin").map((r) => r.value)).toEqual(["admin", "member"]);
  });

  it("only owners can change an owner's role; members change no one", () => {
    expect(canChangeRole("owner", "owner")).toBe(true);
    expect(canChangeRole("admin", "owner")).toBe(false);
    expect(canChangeRole("admin", "member")).toBe(true);
    expect(canChangeRole("member", "member")).toBe(false);
  });
});
