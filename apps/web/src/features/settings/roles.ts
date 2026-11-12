import type { User } from "@/data/types";

type Role = User["role"];

const LABEL: Record<Role, string> = { owner: "Owner", admin: "Admin", member: "Member" };

/**
 * Roles you may give someone, like GitHub and Slack: only owners make (or unmake) owners;
 * admins hand out admin and member. Owners are never invited, only promoted.
 */
export function rolesYouCanGive(yourRole: Role): { value: Role; label: string }[] {
  const roles: Role[] = yourRole === "owner" ? ["owner", "admin", "member"] : ["admin", "member"];
  return roles.map((value) => ({ value, label: LABEL[value] }));
}

/** Can you change this person's role? Members can't change anyone; only owners touch owners. */
export function canChangeRole(yourRole: Role, theirRole: Role) {
  if (yourRole === "member") return false;
  return theirRole !== "owner" || yourRole === "owner";
}

/** Roles for an invite: owners aren't invited, they're made from members. */
export const INVITE_ROLES = rolesYouCanGive("admin");
