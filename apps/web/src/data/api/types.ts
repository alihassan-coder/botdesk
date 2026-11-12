/** Shapes the API sends back (JSON is camelCase). See http://localhost:8000/api/docs. */

export type ApiRole = "owner" | "admin" | "member";

export interface ApiUser {
  id: string;
  name: string;
  email: string;
  handle: string;
}

/** An organization, with the signed-in user's role in it. */
export interface ApiOrg {
  id: string;
  name: string;
  slug: string;
  plan: "self-hosted" | "free" | "pro" | "team";
  role: ApiRole;
}

/** Who is signed in, and which organizations they belong to. */
export interface ApiMe {
  user: ApiUser;
  organizations: ApiOrg[];
}

export interface ApiMember extends ApiUser {
  role: ApiRole;
}

export interface ApiInvitation {
  id: string;
  email: string;
  role: "admin" | "member";
  createdAt: string;
  expiresAt: string;
}

/** Only the answer to creating an invite has the link; it's shown once. */
export interface ApiNewInvitation extends ApiInvitation {
  inviteUrl: string;
}
