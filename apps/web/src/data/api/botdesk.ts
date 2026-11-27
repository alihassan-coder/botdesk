import type { BrowserInput } from "../types";
import { apiBaseUrl, apiFetch } from "./client";
import {
  RUN_EVENT_KINDS,
  type ApiApproval,
  type ApiApprovalStatus,
  type ApiDecision,
  type ApiBot,
  type ApiBotInput,
  type ApiBotTools,
  type ApiBrowser,
  type ApiBrowserProvider,
  type ApiBrowserProviderInput,
  type ApiConnection,
  type ApiConnectionOwner,
  type ApiConnector,
  type ApiInvitation,
  type ApiMcpServer,
  type ApiMcpServerAdded,
  type ApiMcpServerInput,
  type ApiMcpToolChoice,
  type ApiFile,
  type ApiMemory,
  type ApiMemoryKey,
  type ApiMemoryStatus,
  type ApiStorage,
  type ApiStorageInput,
  type ApiMe,
  type ApiMember,
  type ApiMessage,
  type ApiUsage,
  type ApiModelList,
  type ApiModelProvider,
  type ApiNewInvitation,
  type ApiOrg,
  type ApiPlugin,
  type ApiProviderKeyInput,
  type ApiProviderTest,
  type ApiRetentionDays,
  type ApiRole,
  type ApiRoutine,
  type ApiRoutineInput,
  type ApiRunEvent,
  type ApiSecurityLevel,
  type ApiSentMessage,
  type ApiTemplate,
  type ApiThread,
  type ApiThreadRuns,
} from "./types";

/** Every API route the web app uses, one plain function each. Only store.ts calls these. */

export const authApi = {
  /** Public: whether sign-up is open, invite-only or closed on this server. */
  /** `oauthCallbackUrl` is missing from APIs before 2026-11-27. */
  options: () => apiFetch<{ signUpMode: "open" | "invite-only" | "closed"; oauthCallbackUrl?: string }>("/api/v1/auth/options"),
  /** `inviteToken` (from an invite link): join that organization instead of getting your own. */
  signUp: (input: { name: string; email: string; password: string; inviteToken?: string }) =>
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
  /** A new organization; whoever creates it owns it. Without a slug, one is made from the name. */
  create: (input: { name: string; slug?: string }) => apiFetch<ApiOrg>("/api/v1/orgs", { method: "POST", body: input }),
  /**
   * `monthlyBudgetUsd`: null removes the limit. `maxSecurityLevel`: the ceiling for every bot;
   * lowering it below the default lowers the default too. `historyRetentionDays`: null keeps messages
   * forever (left out, it stays as it is). Owners and admins only.
   */
  update: (
    orgId: string,
    patch: {
      name?: string;
      slug?: string;
      monthlyBudgetUsd?: number | null;
      defaultSecurityLevel?: ApiSecurityLevel;
      maxSecurityLevel?: ApiSecurityLevel;
      historySummaries?: boolean;
      historyRetentionDays?: ApiRetentionDays | null;
    },
  ) =>
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

/** The marketplace: the same templates for every organization on this server. */
export const templateApi = {
  list: () => apiFetch<ApiTemplate[]>("/api/v1/templates"),
  /** Creates the template's bot (its instructions, Tools and starting level are the API's call). Open its DM next. */
  hire: (orgId: string, templateId: string) =>
    apiFetch<ApiBot>(`/api/v1/orgs/${orgId}/templates/${templateId}/hire`, { method: "POST" }),
};

export const threadApi = {
  /** Your chats in this organization, most recent first. */
  list: (orgId: string) => apiFetch<ApiThread[]>(`/api/v1/orgs/${orgId}/threads`),
  /** Your chat with a bot: the existing one, or a new one. */
  openDm: (orgId: string, botId: string) => apiFetch<ApiThread>(`/api/v1/orgs/${orgId}/threads/dm`, { method: "POST", body: { botId } }),
  /** A group with you plus the bots and people you pick; they must all be in the org. `leadBotId`
   *  (one of `botIds`) answers messages that mention no bot; left out, the first bot picked leads. */
  createGroup: (orgId: string, group: { title: string; botIds: string[]; userIds: string[]; leadBotId?: string }) =>
    apiFetch<ApiThread>(`/api/v1/orgs/${orgId}/threads/groups`, { method: "POST", body: group }),
  /** Change a group's lead (one of its bots), or clear it with null. Its creator, owners and admins may. */
  setLead: (orgId: string, threadId: string, botId: string | null) =>
    apiFetch<ApiThread>(`/api/v1/orgs/${orgId}/threads/${threadId}/lead`, { method: "PUT", body: { botId } }),
  /** Rename a group (its creator, owners and admins). */
  rename: (orgId: string, threadId: string, title: string) =>
    apiFetch<ApiThread>(`/api/v1/orgs/${orgId}/threads/${threadId}`, { method: "PATCH", body: { title } }),
  /** Add people and bots of the org to a group (its creator, owners and admins). */
  addParticipants: (orgId: string, threadId: string, add: { userIds: string[]; botIds: string[] }) =>
    apiFetch<ApiThread>(`/api/v1/orgs/${orgId}/threads/${threadId}/participants`, { method: "POST", body: add }),
  /** Remove a person or a bot from a group. Removing the lead bot clears the lead. */
  removeParticipant: (orgId: string, threadId: string, type: "user" | "bot", id: string) =>
    apiFetch<ApiThread>(`/api/v1/orgs/${orgId}/threads/${threadId}/participants/${type}/${id}`, { method: "DELETE" }),
  /** You've read the chat up to now: its unread count drops to 0. */
  markRead: (orgId: string, threadId: string) => apiFetch<void>(`/api/v1/orgs/${orgId}/threads/${threadId}/read`, { method: "POST" }),
  /** Oldest first. For older ones, pass the first message's createdAt as `before` and its id as `beforeId`. */
  messages: (orgId: string, threadId: string, { limit, before, beforeId }: { limit: number; before?: string; beforeId?: string }) => {
    const query = new URLSearchParams({ limit: String(limit), ...(before ? { before } : {}), ...(before && beforeId ? { beforeId } : {}) });
    return apiFetch<ApiMessage[]>(`/api/v1/orgs/${orgId}/threads/${threadId}/messages?${query}`);
  },
  /**
   * Who replies: see ADR 0009 (a DM's bot and guests, a group's mentioned bots or lead). Replies arrive on the event stream.
   * `attachments`: up to 10 uploaded files by id (a DM: the bot's own or shared ones; a group: shared ones); text may then be empty.
   */
  send: (orgId: string, threadId: string, text: string, attachments: string[] = []) =>
    apiFetch<ApiSentMessage>(`/api/v1/orgs/${orgId}/threads/${threadId}/messages`, {
      method: "POST", body: attachments.length > 0 ? { text, attachments } : { text },
    }),

  /** The chat's runs that haven't finished (queued, running or paused), and where its event stream is. */
  activeRuns: (orgId: string, threadId: string) =>
    apiFetch<ApiThreadRuns>(`/api/v1/orgs/${orgId}/threads/${threadId}/runs?active=true`),

  /**
   * Live updates for one chat (Server-Sent Events), after event `after` (a `lastEventId`
   * from activeRuns), or from now on without it. If the connection drops, the browser
   * reconnects by itself and the API resumes after the last event it saw (the
   * Last-Event-ID header). Returns a function that closes the stream.
   */
  follow(orgId: string, threadId: string, onEvent: (event: ApiRunEvent) => void, after?: number): () => void {
    const query = after === undefined ? "" : `?after=${after}`;
    const source = new EventSource(`${apiBaseUrl()}/api/v1/orgs/${orgId}/threads/${threadId}/events${query}`, { withCredentials: true });
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
  /** It was done / It wasn't done, for a run that needs attention: the run then carries on. */
  resolve: (orgId: string, runId: string, outcome: "done" | "not_done") =>
    apiFetch<unknown>(`/api/v1/orgs/${orgId}/runs/${runId}/resolve`, { method: "POST", body: { outcome } }),
};

/** Connect apps: the plugins the server loaded. */
export const pluginApi = {
  /** The plugins this server loaded, with each tool's risk. Any member. */
  list: (orgId: string) => apiFetch<ApiPlugin[]>(`/api/v1/orgs/${orgId}/plugins`),
};

/** Connect apps: connectors, the accounts connected to them, and which plugins each bot uses. */
export const connectionApi = {
  connectors: (orgId: string) => apiFetch<ApiConnector[]>(`/api/v1/orgs/${orgId}/connectors`),
  /** The connections you may see: yours, the bots' and the organization's. */
  list: (orgId: string) => apiFetch<ApiConnection[]>(`/api/v1/orgs/${orgId}/connections`),
  /** The provider's sign-in page to send the browser to; it comes back through the API's callback. */
  startOAuth: (orgId: string, input: ApiConnectionOwner & { connectorId: string; access?: string }) =>
    apiFetch<{ authorizeUrl: string }>(`/api/v1/orgs/${orgId}/connections/oauth/start`, { method: "POST", body: input }),
  /** The key goes in once and never comes back out. */
  connectApiKey: (orgId: string, input: ApiConnectionOwner & { connectorId: string; accountLabel: string; apiKey: string }) =>
    apiFetch<ApiConnection>(`/api/v1/orgs/${orgId}/connections`, { method: "POST", body: input }),
  /** Forgets the credential (and revokes it at the provider). */
  disconnect: (orgId: string, connectionId: string) =>
    apiFetch<void>(`/api/v1/orgs/${orgId}/connections/${connectionId}`, { method: "DELETE" }),
  botTools: (orgId: string, botId: string) => apiFetch<ApiBotTools>(`/api/v1/orgs/${orgId}/bots/${botId}/tools`),
  /** Only the plugins sent change. */
  setBotTools: (orgId: string, botId: string, plugins: { pluginId: string; enabled: boolean; connectionId: string | null }[]) =>
    apiFetch<ApiBotTools>(`/api/v1/orgs/${orgId}/bots/${botId}/tools`, { method: "PUT", body: { plugins } }),
  /** Switch a plugin's trigger ("new_email") on for you, or off. Returns the bot's tools. */
  setBotTrigger: (orgId: string, botId: string, pluginId: string, trigger: string, enabled: boolean) =>
    apiFetch<ApiBotTools>(`/api/v1/orgs/${orgId}/bots/${botId}/tools/${pluginId}/triggers/${trigger}`, { method: "PUT", body: { enabled } }),
};

/** An organization's MCP servers (ADR 0012). Every member lists; owners and admins change. */
export const mcpApi = {
  list: (orgId: string) => apiFetch<ApiMcpServer[]>(`/api/v1/orgs/${orgId}/mcp-servers`),
  /** Connects, lists the tools and saves them. Keys and client secrets go in once and never come back out.
   * A server that wants a sign-in comes back with `authorizeUrl`. */
  add: (orgId: string, input: ApiMcpServerInput) =>
    apiFetch<ApiMcpServerAdded>(`/api/v1/orgs/${orgId}/mcp-servers`, { method: "POST", body: input }),
  /** Lists the tools again; changed and new ones wait for the review. */
  refresh: (orgId: string, serverId: string) =>
    apiFetch<ApiMcpServer>(`/api/v1/orgs/${orgId}/mcp-servers/${serverId}/refresh`, { method: "POST" }),
  /** The review screen's save: approve these tools as they are, on or off, at these risks. 409 if they changed since `toolsHash`. */
  reviewTools: (orgId: string, serverId: string, body: { toolsHash: string; tools: ApiMcpToolChoice[] }) =>
    apiFetch<ApiMcpServer>(`/api/v1/orgs/${orgId}/mcp-servers/${serverId}/tools`, { method: "PUT", body }),
  /** Sign in (or reconnect) the organization's OAuth sign-in: where to send the browser. */
  signIn: (orgId: string, serverId: string) =>
    apiFetch<{ authorizeUrl: string }>(`/api/v1/orgs/${orgId}/mcp-servers/${serverId}/sign-in`, { method: "POST" }),
  remove: (orgId: string, serverId: string) =>
    apiFetch<void>(`/api/v1/orgs/${orgId}/mcp-servers/${serverId}`, { method: "DELETE" }),
};

export const usageApi = {
  /** Daily totals for the last `days` UTC days, this month's total, and every bot's spend. Any member. */
  org: (orgId: string, days = 14) => apiFetch<ApiUsage>(`/api/v1/orgs/${orgId}/usage?days=${days}`),
};

/** Settings → Models & keys. Everyone may read; owners and admins change keys. Keys go in, never come back out. */
export const modelApi = {
  providers: (orgId: string) => apiFetch<ApiModelProvider[]>(`/api/v1/orgs/${orgId}/providers`),
  /** Checked live before it's saved; a key that doesn't work comes back as a 400 saying why. "custom" adds a new server. */
  saveKey: (orgId: string, providerId: string, input: ApiProviderKeyInput) =>
    apiFetch<ApiModelProvider>(`/api/v1/orgs/${orgId}/providers/${providerId}`, { method: "PUT", body: input }),
  testKey: (orgId: string, providerId: string) =>
    apiFetch<ApiProviderTest>(`/api/v1/orgs/${orgId}/providers/${providerId}/test`, { method: "POST" }),
  removeKey: (orgId: string, providerId: string) =>
    apiFetch<void>(`/api/v1/orgs/${orgId}/providers/${providerId}`, { method: "DELETE" }),
  /** My keys: your own key per built-in provider in this org (last 4 characters only). Only you see them; they serve only your runs. */
  myKeys: (orgId: string) => apiFetch<ApiModelProvider[]>(`/api/v1/orgs/${orgId}/me/providers`),
  /** Any member; checked live before it's saved, like the org's keys. */
  saveMyKey: (orgId: string, providerId: string, apiKey: string) =>
    apiFetch<ApiModelProvider>(`/api/v1/orgs/${orgId}/me/providers/${providerId}`, { method: "PUT", body: { apiKey } }),
  /** Check your own saved key again (yours only; 404 if you have none). */
  testMyKey: (orgId: string, providerId: string) =>
    apiFetch<ApiProviderTest>(`/api/v1/orgs/${orgId}/me/providers/${providerId}/test`, { method: "POST" }),
  removeMyKey: (orgId: string, providerId: string) =>
    apiFetch<void>(`/api/v1/orgs/${orgId}/me/providers/${providerId}`, { method: "DELETE" }),
  /** Every connected provider's models, live (cached ~10 minutes on the API unless `refresh`), as your runs reach them: your own key first. */
  models: (orgId: string, refresh = false) =>
    apiFetch<ApiModelList>(`/api/v1/orgs/${orgId}/models${refresh ? "?refresh=true" : ""}`),
};

/** Bots' files and where the organization keeps them (ADR 0017). Any member reads, uploads and deletes files. */
export const fileApi = {
  storage: (orgId: string) => apiFetch<ApiStorage>(`/api/v1/orgs/${orgId}/storage`),
  /** Owners and admins. Checked with a live write, read and delete first (it can take a few seconds); a 400 says why it didn't work. */
  chooseStorage: (orgId: string, input: ApiStorageInput) =>
    apiFetch<ApiStorage>(`/api/v1/orgs/${orgId}/storage`, { method: "PUT", body: input }),
  /** A bot's files by path; without `botId`, the shared ones. */
  list: (orgId: string, botId?: string) =>
    apiFetch<ApiFile[]>(`/api/v1/orgs/${orgId}/files${botId ? `?botId=${encodeURIComponent(botId)}` : ""}`),
  /**
   * Into the bot's folder (the shared one without `botId`), at `path` or else the file's name. Saving
   * the same path again replaces it, unless `keepBoth`: then the API picks a free name ("q3 (2).pdf").
   */
  upload: (orgId: string, file: File, botId?: string, path?: string, keepBoth = false) => {
    const form = new FormData();
    form.append("file", file);
    if (botId) form.append("botId", botId);
    if (path) form.append("path", path);
    if (keepBoth) form.append("keepBoth", "true");
    return apiFetch<ApiFile>(`/api/v1/orgs/${orgId}/files`, { method: "POST", body: form });
  },
  remove: (orgId: string, fileId: string) => apiFetch<void>(`/api/v1/orgs/${orgId}/files/${fileId}`, { method: "DELETE" }),
  /** The file's bytes, for a link or an <img>: the session cookie goes with it (same site). */
  contentUrl: (orgId: string, fileId: string) => `${apiBaseUrl()}/api/v1/orgs/${orgId}/files/${fileId}/content`,
};

/** Where the org's bots' browsers run (owners and admins choose), and a bot's browser (ADR 0017 §5): watch it and take over, for example to sign in. Any member. */
export const browserApi = {
  /** Where bots' browsers run: Local or a cloud provider. */
  provider: (orgId: string) => apiFetch<ApiBrowserProvider>(`/api/v1/orgs/${orgId}/browser-provider`),
  /** Owners and admins. A cloud provider is checked by starting and stopping a browser there (a few seconds); a 400 says why it didn't work. */
  chooseProvider: (orgId: string, input: ApiBrowserProviderInput) =>
    apiFetch<ApiBrowserProvider>(`/api/v1/orgs/${orgId}/browser-provider`, { method: "PUT", body: input }),
  state: (orgId: string, botId: string) => apiFetch<ApiBrowser>(`/api/v1/orgs/${orgId}/bots/${botId}/browser`),
  /** The screen now (JPEG), for an <img>: the session cookie goes with it. 400 when the browser isn't open. */
  screenUrl: (orgId: string, botId: string) => `${apiBaseUrl()}/api/v1/orgs/${orgId}/bots/${botId}/browser/screen`,
  /** A click (page pixels), text, a key, a scroll, or an address to open (which starts it). Answers the state; 400 says why it can't. */
  input: (orgId: string, botId: string, input: BrowserInput) =>
    apiFetch<ApiBrowser>(`/api/v1/orgs/${orgId}/bots/${botId}/browser/input`, { method: "POST", body: input }),
  /** Close it and forget every sign-in (its profile is deleted). */
  forget: (orgId: string, botId: string) => apiFetch<void>(`/api/v1/orgs/${orgId}/bots/${botId}/browser`, { method: "DELETE" }),
};

/** What a bot remembers. Members see the bot's shared memories and their own DM ones. */
export const memoryApi = {
  status: (orgId: string) => apiFetch<ApiMemoryStatus>(`/api/v1/orgs/${orgId}/memory/status`),
  /** The organization's memory key (OpenAI or Gemini, used only for memory): its last 4 characters, never the key. Any member. */
  key: (orgId: string) => apiFetch<ApiMemoryKey>(`/api/v1/orgs/${orgId}/memory-key`),
  /** Owners and admins. Checked live first; a key that doesn't work comes back as a 400 saying why. */
  saveKey: (orgId: string, input: { provider: "openai" | "gemini"; apiKey: string }) =>
    apiFetch<ApiMemoryKey>(`/api/v1/orgs/${orgId}/memory-key`, { method: "PUT", body: input }),
  /** Owners and admins. Memory goes back to the server's key, if it has one. */
  removeKey: (orgId: string) => apiFetch<void>(`/api/v1/orgs/${orgId}/memory-key`, { method: "DELETE" }),
  /** Everything, newest first; or with a query, the closest matches first. */
  list: (orgId: string, botId: string, query = "") =>
    apiFetch<ApiMemory[]>(`/api/v1/orgs/${orgId}/bots/${botId}/memories${query ? `?q=${encodeURIComponent(query)}` : ""}`),
  correct: (orgId: string, botId: string, memoryId: string, text: string) =>
    apiFetch<ApiMemory>(`/api/v1/orgs/${orgId}/bots/${botId}/memories/${memoryId}`, { method: "PATCH", body: { text } }),
  forget: (orgId: string, botId: string, memoryId: string) =>
    apiFetch<void>(`/api/v1/orgs/${orgId}/bots/${botId}/memories/${memoryId}`, { method: "DELETE" }),
  /** Owners and admins only: the bot forgets everything, from every chat. */
  forgetAll: (orgId: string, botId: string) => apiFetch<void>(`/api/v1/orgs/${orgId}/bots/${botId}/memories`, { method: "DELETE" }),
};

/** Routines: a bot repeats a task on a schedule, in its creator's DM. */
export const routineApi = {
  list: (orgId: string) => apiFetch<ApiRoutine[]>(`/api/v1/orgs/${orgId}/routines`),
  create: (orgId: string, routine: ApiRoutineInput) =>
    apiFetch<ApiRoutine>(`/api/v1/orgs/${orgId}/routines`, { method: "POST", body: routine }),
  /** Switch it on or off, or edit it: only the fields sent change. Its creator, owners and admins. */
  update: (orgId: string, routineId: string, patch: Partial<ApiRoutineInput>) =>
    apiFetch<ApiRoutine>(`/api/v1/orgs/${orgId}/routines/${routineId}`, { method: "PATCH", body: patch }),
  remove: (orgId: string, routineId: string) =>
    apiFetch<void>(`/api/v1/orgs/${orgId}/routines/${routineId}`, { method: "DELETE" }),
  /** Run it once now, in its creator's DM. 409 while its last run is still going. */
  runNow: (orgId: string, routineId: string) =>
    apiFetch<{ runId: string; threadId: string }>(`/api/v1/orgs/${orgId}/routines/${routineId}/run-now`, { method: "POST" }),
};
