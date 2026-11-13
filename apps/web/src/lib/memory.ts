import type { MemoryItem, User } from "@/data/types";

type Role = User["role"];

/**
 * Who may forget or correct a memory. Owners and admins: anything the bot remembers.
 * Members: only what it learned in their own DM, since group-chat memories are the team's.
 */
export function canChangeMemory(role: Role, memory: Pick<MemoryItem, "scope">) {
  return role !== "member" || memory.scope === "you";
}

/** Making a bot forget everything takes an owner or admin. */
export function canForgetEverything(role: Role) {
  return role !== "member";
}
