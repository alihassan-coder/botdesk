import type { User } from "@/data/types";

/** Roles you can give someone here. Owner isn't one: owners are made from existing members. */
export const ROLES: { value: Exclude<User["role"], "owner">; label: string }[] = [
  { value: "admin", label: "Admin" },
  { value: "member", label: "Member" },
];
