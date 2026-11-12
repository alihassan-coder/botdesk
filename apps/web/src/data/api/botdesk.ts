import { apiFetch } from "./client";
import type { ApiBot, ApiBotInput, ApiInvitation, ApiMe, ApiMember, ApiNewInvitation, ApiOrg, ApiRole } from "./types";

/** Every API route the web app uses, one plain function each. Only store.ts calls these. */

export const authApi = {
  signUp: (input: { name: string; email: string; password: string }) =>
    apiFetch<ApiMe>("/api/v1/auth/sign-up", { method: "POST", body: input }),
  signIn: (email: string, password: string) =>
    apiFetch<ApiMe>("/api/v1/auth/sign-in", { method: "POST", body: { email, password } }),
  signOut: () => apiFetch<void>("/api/v1/auth/sign-out", { method: "POST" }),
  me: () => apiFetch<ApiMe>("/api/v1/auth/me"),
  forgotPassword: (email: string) =>
    apiFetch<{ message: string }>("/api/v1/auth/forgot-password", { method: "POST", body: { email } }),
  /** Set a new password from an emailed reset link. Works once; signs out every device. */
  resetPassword: (token: string, password: string) =>
    apiFetch<{ message: string }>("/api/v1/auth/reset-password", { method: "POST", body: { token, password } }),
};

export const orgApi = {
  update: (orgId: string, patch: { name?: string; slug?: string }) =>
    apiFetch<ApiOrg>(`/api/v1/orgs/${orgId}`, { method: "PATCH", body: patch }),
  members: (orgId: string) => apiFetch<ApiMember[]>(`/api/v1/orgs/${orgId}/members`),
  changeRole: (orgId: string, userId: string, role: ApiRole) =>
    apiFetch<ApiMember>(`/api/v1/orgs/${orgId}/members/${userId}`, { method: "PATCH", body: { role } }),
  /** Remove someone, or leave the org when it's your own id. */
  removeMember: (orgId: string, userId: string) =>
    apiFetch<void>(`/api/v1/orgs/${orgId}/members/${userId}`, { method: "DELETE" }),
};

export const inviteApi = {
  list: (orgId: string) => apiFetch<ApiInvitation[]>(`/api/v1/orgs/${orgId}/invitations`),
  create: (orgId: string, invite: { email: string; role: "admin" | "member" }) =>
    apiFetch<ApiNewInvitation>(`/api/v1/orgs/${orgId}/invitations`, { method: "POST", body: invite }),
  revoke: (orgId: string, invitationId: string) =>
    apiFetch<void>(`/api/v1/orgs/${orgId}/invitations/${invitationId}`, { method: "DELETE" }),
  /** Join the org the invite is for; must be signed in with the invited email. */
  accept: (token: string) => apiFetch<ApiOrg>("/api/v1/invitations/accept", { method: "POST", body: { token } }),
};

export const botApi = {
  list: (orgId: string) => apiFetch<ApiBot[]>(`/api/v1/orgs/${orgId}/bots`),
  /** Only the name is required; the API has defaults for the rest. */
  create: (orgId: string, bot: Partial<ApiBotInput>) => apiFetch<ApiBot>(`/api/v1/orgs/${orgId}/bots`, { method: "POST", body: bot }),
  /** Only the fields you send change. A new name gets a matching @handle. */
  update: (orgId: string, botId: string, patch: Partial<ApiBotInput>) =>
    apiFetch<ApiBot>(`/api/v1/orgs/${orgId}/bots/${botId}`, { method: "PATCH", body: patch }),
  /** Owners and admins only. */
  remove: (orgId: string, botId: string) => apiFetch<void>(`/api/v1/orgs/${orgId}/bots/${botId}`, { method: "DELETE" }),
};
