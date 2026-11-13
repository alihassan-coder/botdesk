import { apiBaseUrl, apiFetch } from "./client";
import {
  RUN_EVENT_KINDS,
  type ApiApproval,
  type ApiApprovalStatus,
  type ApiDecision,
  type ApiBot,
  type ApiBotInput,
  type ApiInvitation,
  type ApiMe,
  type ApiMember,
  type ApiMessage,
  type ApiNewInvitation,
  type ApiOrg,
  type ApiRole,
  type ApiRunEvent,
  type ApiSentMessage,
  type ApiThread,
} from "./types";

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
  /** Change your name or @handle. */
  updateProfile: (patch: { name?: string; handle?: string }) => apiFetch<ApiMe>("/api/v1/auth/me", { method: "PATCH", body: patch }),
  /** Keeps you signed in here and signs out your other devices. */
  changePassword: (currentPassword: string, newPassword: string) =>
    apiFetch<{ message: string }>("/api/v1/auth/change-password", { method: "POST", body: { currentPassword, newPassword } }),
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

export const threadApi = {
  /** Your chats in this organization, most recent first. */
  list: (orgId: string) => apiFetch<ApiThread[]>(`/api/v1/orgs/${orgId}/threads`),
  /** Your chat with a bot: the existing one, or a new one. */
  openDm: (orgId: string, botId: string) => apiFetch<ApiThread>(`/api/v1/orgs/${orgId}/threads/dm`, { method: "POST", body: { botId } }),
  /** A group with you plus the bots and people you pick; they must all be in the org. */
  createGroup: (orgId: string, group: { title: string; botIds: string[]; userIds: string[] }) =>
    apiFetch<ApiThread>(`/api/v1/orgs/${orgId}/threads/groups`, { method: "POST", body: group }),
  /** Oldest first. For older ones, pass the first message's createdAt as `before`. */
  messages: (orgId: string, threadId: string, { limit, before }: { limit: number; before?: string }) => {
    const query = new URLSearchParams({ limit: String(limit), ...(before ? { before } : {}) });
    return apiFetch<ApiMessage[]>(`/api/v1/orgs/${orgId}/threads/${threadId}/messages?${query}`);
  },
  /** In a DM the bot replies; in a group, the bots you @mention do. Replies arrive on the event stream. */
  send: (orgId: string, threadId: string, text: string) =>
    apiFetch<ApiSentMessage>(`/api/v1/orgs/${orgId}/threads/${threadId}/messages`, { method: "POST", body: { text } }),

  /**
   * Live updates for one chat (Server-Sent Events), from now on. If the connection drops,
   * the browser reconnects by itself and the API resumes after the last event it saw
   * (the Last-Event-ID header). Returns a function that closes the stream.
   */
  follow(orgId: string, threadId: string, onEvent: (event: ApiRunEvent) => void): () => void {
    const source = new EventSource(`${apiBaseUrl()}/api/v1/orgs/${orgId}/threads/${threadId}/events`, { withCredentials: true });
    const handle = (message: MessageEvent<string>) => {
      try {
        onEvent(JSON.parse(message.data) as ApiRunEvent);
      } catch {
        // A line we can't read: skip it rather than break the chat.
      }
    };
    for (const kind of RUN_EVENT_KINDS) source.addEventListener(kind, handle);
    return () => source.close();
  },
};

export const approvalApi = {
  /** Approvals in chats you're in, newest first (at most 100). */
  list: (orgId: string, filter: { status?: ApiApprovalStatus | "all"; botId?: string; threadId?: string } = {}) => {
    const query = new URLSearchParams(Object.entries(filter).filter((entry): entry is [string, string] => Boolean(entry[1])));
    return apiFetch<ApiApproval[]>(`/api/v1/orgs/${orgId}/approvals?${query}`);
  },
  get: (orgId: string, approvalId: string) => apiFetch<ApiApproval>(`/api/v1/orgs/${orgId}/approvals/${approvalId}`),
  /** Decides once: 409 if someone already did (or it expired), 400 if edited args don't fit the tool. */
  decide: (orgId: string, approvalId: string, decision: ApiDecision) =>
    apiFetch<ApiApproval>(`/api/v1/orgs/${orgId}/approvals/${approvalId}/decide`, { method: "POST", body: decision }),
};

export const runApi = {
  /** The Stop button: a queued or paused run stops at once, a running one within moments. */
  cancel: (orgId: string, runId: string) => apiFetch<unknown>(`/api/v1/orgs/${orgId}/runs/${runId}/cancel`, { method: "POST" }),
};
