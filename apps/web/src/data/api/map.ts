import type { Invitation, Org, User } from "../types";
import type { ApiInvitation, ApiOrg, ApiRole, ApiUser } from "./types";

/**
 * Turns API answers into the web app's own types, so screens never see API shapes.
 * A person's role belongs to their membership in an org, so it's passed in.
 * The API has no presence yet, so everyone shows as online.
 */
export function toUser({ id, name, email, handle }: ApiUser, role: ApiRole): User {
  return { id, name, email, handle, role, presence: "online" };
}

export function toOrg({ id, name, slug, plan }: ApiOrg): Org {
  return { id, name, slug, plan };
}

/** Drops the one-time invite link, so it never sits in the store. */
export function toInvitation({ id, email, role, createdAt, expiresAt }: ApiInvitation): Invitation {
  return { id, email, role, createdAt, expiresAt };
}
