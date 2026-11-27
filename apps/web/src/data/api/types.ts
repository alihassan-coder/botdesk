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
  role: ApiRole;
  /** null = no limit. */
  monthlyBudgetUsd?: number | null;
  defaultSecurityLevel: ApiSecurityLevel;
  /** The ceiling: no bot here acts above it ("autonomous" = none). */
  maxSecurityLevel: ApiSecurityLevel;
  /** Chat history (ADR 0019). Left out by an older API: summaries on, messages kept forever. */
  historySummaries?: boolean;
  /** null = keep messages forever. */
  historyRetentionDays?: ApiRetentionDays | null;
}

export type ApiRetentionDays = 30 | 90 | 180 | 365;

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

export type ApiSecurityLevel = "read-only" | "ask-before-acting" | "autonomous";

/** A marketplace template (`GET /templates`). */
export interface ApiTemplate {
  id: string;
  name: string;
  role: string;
  category: string;
  description: string;
  instructions: string;
  avatarColor: ApiBot["avatarColor"];
  securityLevel: ApiSecurityLevel;
  /** Plugin ids this server loaded that the template works in. */
  plugins: string[];
}

export interface ApiBot {
  id: string;
  name: string;
  handle: string;
  role: string;
  description: string;
  instructions: string;
  avatarColor: "indigo" | "violet" | "sky" | "emerald" | "amber" | "rose" | "orange" | "slate";
  /** "provider:model", or "" for the organization's default model. */
  modelId: string;
  securityLevel: ApiSecurityLevel;
  monthlyBudgetUsd: number;
  memoryEnabled: boolean;
  status: "idle" | "working" | "waiting-approval" | "sleeping" | "error";
  createdAt: string;
}

/** What you send to hire or edit a bot; the API fills in id, handle, status and createdAt. */
export type ApiBotInput = Pick<
  ApiBot,
  "name" | "role" | "description" | "instructions" | "avatarColor" | "modelId" | "securityLevel" | "monthlyBudgetUsd" | "memoryEnabled"
>;

/* ---------- Usage and budgets ---------- */

export interface ApiUsageDay {
  date: string;
  modelsUsd: number;
  computersUsd: number;
  inputTokens: number;
  outputTokens: number;
  unpricedTokens: number;
}

/** A bot's spend this calendar month (UTC). `budgetUsd` null = no limit. */
export interface ApiBotSpend {
  botId: string;
  name: string;
  spentUsd: number;
  budgetUsd: number | null;
  inputTokens: number;
  outputTokens: number;
  unpricedTokens: number;
}

export interface ApiUsage {
  days: ApiUsageDay[];
  monthStart: string;
  monthToDateUsd: number;
  orgBudgetUsd: number | null;
  unpricedTokens: number;
  bots: ApiBotSpend[];
  pricesChecked: string;
}

/* ---------- Models & keys ---------- */

export interface ApiModelProvider {
  id: string;
  kind: "anthropic" | "openai" | "gemini" | "openrouter" | "groq" | "custom";
  name: string;
  hint: string;
  connected: boolean;
  /** "member": your own key (My keys), only ever in your own list. */
  source: "org" | "member" | "env" | null;
  keyHint: string | null;
  status: "ok" | "invalid" | null;
  lastVerifiedAt: string | null;
  baseUrl: string | null;
}

/**
 * Add or replace a key. Custom servers also send a base URL and a name; their key may be "".
 * Editing a custom server: "" keeps the saved key while the base URL is unchanged; a new base URL
 * needs the key again, or `noKey: true` to drop it.
 */
export interface ApiProviderKeyInput {
  apiKey: string;
  baseUrl?: string;
  label?: string;
  noKey?: boolean;
}

export interface ApiProviderTest {
  ok: boolean;
  error: string | null;
  provider: ApiModelProvider;
}

export interface ApiModel {
  id: string;
  provider: string;
  name: string;
  contextWindow: number | null;
  pricing: { inputPerMtok: number; outputPerMtok: number } | null;
}

export interface ApiModelList {
  models: ApiModel[];
  errors: { provider: string; message: string }[];
}

/* ---------- Chats ---------- */

export interface ApiThread {
  id: string;
  kind: "dm" | "group";
  title: string;
  /** For DMs, the bot the chat is with. */
  botId: string | null;
  /** Groups: the bot that answers a message that mentions no bot. Always null for a DM. */
  leadBotId: string | null;
  /** Who started the chat (null if their account is gone). */
  createdBy: string | null;
  participants: { type: "user" | "bot"; id: string }[];
  lastMessageAt: string;
  /** "" until the chat has a message. */
  lastMessagePreview: string;
  /** Messages after you last read the chat that someone else wrote. Left out of `thread_updated`. */
  unread?: number;
}

export interface ApiMessage {
  id: string;
  threadId: string;
  /** `id` is null for system messages. */
  author: { type: "user" | "bot" | "system"; id: string | null };
  /** Message parts as stored; only some types are known to the web app. */
  parts: Record<string, unknown>[];
  status: "streaming" | "complete" | "error";
  createdAt: string;
}

/** The message you sent, plus one run per bot that will reply. */
export interface ApiSentMessage extends ApiMessage {
  runIds: string[];
}

/* ---------- Runs ---------- */

export type ApiRunStatus =
  | "queued" | "running" | "waiting_approval" | "needs_attention" | "waiting_handoff" | "succeeded" | "failed" | "cancelled";

/** A handed-off Task (TaskOut, ADR 0014): the `task_updated` event's `data.task`. */
export interface ApiTask {
  id: string;
  threadId: string;
  parentRunId: string;
  childRunId: string | null;
  /** The message holding the Task's handoff card. */
  messageId: string | null;
  fromBotId: string | null;
  /** Null once the bot is removed (the Task stays). */
  toBotId: string | null;
  task: string;
  status: "queued" | "working" | "done" | "failed" | "cancelled";
  resultMessageId: string | null;
  resultPreview: string | null;
  error: string | null;
  errorCode: "budget" | "timeout" | "stopped" | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  deadlineAt: string;
}

/** One piece of work by one bot, from a message to its reply. */
export interface ApiRun {
  id: string;
  botId: string;
  threadId: string;
  triggerMessageId: string | null;
  replyMessageId: string | null;
  status: ApiRunStatus;
  stepsUsed: number;
  maxSteps: number;
  maxSeconds: number;
  /** Why it failed, or why it needs attention. */
  error: string | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

/** A chat's runs, and its newest event id: follow the stream after it and nothing is missed. */
export interface ApiThreadRuns {
  runs: ApiRun[];
  /** The chat's newest event when the runs were read. */
  lastEventId: number;
  /** Just before the unfinished runs' first events: following from here replays them. */
  replayFrom: number;
}

/* ---------- Approvals ---------- */

export type ApiRiskClass = "read" | "write-internal" | "write-external" | "external-send" | "spend" | "destructive" | "credential";
export type ApiApprovalStatus = "pending" | "approved" | "edited" | "denied" | "expired";

/** A tool call paused until a person decides. Same shape in the list, `decide` and the events. */
export interface ApiApproval {
  id: string;
  runId: string;
  threadId: string;
  botId: string;
  toolExecutionId: string;
  /** Plugin id + tool name, like "demo.send_email". */
  tool: string;
  title: string;
  summary: string;
  riskClass: ApiRiskClass;
  reason: string;
  tainted: boolean;
  args: Record<string, unknown>;
  finalArgs: Record<string, unknown> | null;
  /** JSON Schema of the tool's arguments; null if the tool is gone. */
  argsSchema: Record<string, unknown> | null;
  preview: { label: string; value: string }[];
  status: ApiApprovalStatus;
  requestedAt: string;
  expiresAt: string;
  decidedAt: string | null;
  decidedBy: { id: string; name: string } | null;
}

export type ApiDecision = { decision: "approve" | "deny"; editedArgs?: Record<string, unknown> };

/**
 * One live update from `GET /threads/{id}/events` (the SSE `data:` line).
 * The SSE `event:` name is the same as `kind`, and the SSE `id:` the same as `id`.
 */
export type ApiRunEvent = {
  id: number;
  runId: string | null;
  threadId: string;
  createdAt: string;
} & (
  | { kind: "message_saved"; data: { message: ApiMessage } }
  | { kind: "run_started"; data: { botId: string } }
  | { kind: "message_delta"; data: { messageId: string; botId: string; text: string } }
  | { kind: "run_finished"; data: { status: "succeeded" | "cancelled" } }
  /** `code` "budget": the bot or the org reached its monthly budget. */
  | { kind: "run_failed"; data: { status: "failed"; error: string; code?: "budget" } }
  | { kind: "tool_started"; data: { toolExecutionId: string; tool: string; risk: ApiRiskClass; args: Record<string, unknown> } }
  | {
      kind: "tool_finished";
      data: { toolExecutionId: string; tool: string; status: "succeeded" | "failed" | "denied" | "unknown"; result: unknown; error: string | null };
    }
  | { kind: "approval_requested"; data: { approval: ApiApproval } }
  | { kind: "approval_decided"; data: { approval: ApiApproval } }
  /** `after` is missing on older events: read it as "approval". "attention": a person said whether a half-run call was done. */
  | { kind: "run_resumed"; data: { botId: string; after?: "approval" | "tasks" | "attention" } }
  | { kind: "run_needs_attention"; data: { status: "needs_attention"; error: string } }
  /** Sent on the parent run: a Task was created, started or ended. */
  | { kind: "task_updated"; data: { task: ApiTask } }
  /** The parent run paused until the Tasks it handed off have ended. */
  | { kind: "run_waiting_handoff"; data: { status: "waiting_handoff"; taskIds: string[] } }
  /** A group was renamed, or people or bots were added or removed (no unread count: the stream is shared). */
  | { kind: "thread_updated"; data: { thread: ApiThread } }
);

export const RUN_EVENT_KINDS = [
  "message_saved", "run_started", "message_delta", "run_finished", "run_failed",
  "tool_started", "tool_finished", "approval_requested", "approval_decided", "run_resumed", "run_needs_attention",
  "task_updated", "run_waiting_handoff", "thread_updated",
] as const satisfies readonly ApiRunEvent["kind"][];

/* ---------- Files and storage (ADR 0017) ---------- */

export interface ApiS3Storage {
  endpoint: string;
  region: string;
  bucket: string;
  prefix: string;
  accessKeyHint: string;
}

/** GET/PUT /orgs/{id}/storage. */
export interface ApiStorage {
  provider: "local" | "s3" | "cloudinary";
  s3: ApiS3Storage | null;
  /** An API from before Cloudinary sends none. */
  cloudinary?: { cloudName: string; apiKeyHint: string } | null;
  localAvailable: boolean;
  checkedAt: string | null;
}

/** What PUT /storage takes. `secretAccessKey` left out keeps the saved one (storage that is already S3). */
export type ApiStorageInput =
  | { provider: "local" }
  | { provider: "s3"; s3: { endpoint?: string; region: string; bucket: string; prefix?: string; accessKeyId: string; secretAccessKey?: string } }
  | { provider: "cloudinary"; cloudinary: { cloudName: string; apiKey: string; apiSecret?: string } };

export interface ApiFile {
  id: string;
  botId: string | null;
  path: string;
  folder: string;
  contentType: string;
  sizeBytes: number;
  available: boolean;
  createdAt: string;
  updatedAt: string;
}

/** GET/PUT /orgs/{id}/browser-provider. */
export interface ApiBrowserProvider {
  provider: "local" | "steel" | "browserbase" | "kernel";
  keyHint: string | null;
  projectId: string;
  localAvailable: boolean;
  checkedAt: string | null;
}

/** What PUT /browser-provider takes. `apiKey` left out keeps the saved one (the same provider). `projectId`: Browserbase only. */
export type ApiBrowserProviderInput =
  | { provider: "local" }
  | { provider: "steel" | "browserbase" | "kernel"; apiKey?: string; projectId?: string };

/** GET /orgs/{id}/bots/{botId}/browser, and what POST …/browser/input answers. */
export interface ApiBrowser {
  available: boolean;
  open: boolean;
  url: string | null;
  title: string | null;
  width: number;
  height: number;
}

/* ---------- Memory ---------- */

export interface ApiMemory {
  id: string;
  text: string;
  createdAt: string | null;
  updatedAt: string | null;
  /** "bot": learned in group chats; "you": learned in your own DM with the bot. */
  scope: "bot" | "you";
}

export interface ApiMemoryStatus {
  enabled: boolean;
  reason: string | null;
}

/** GET/PUT /orgs/{id}/memory-key. provider null: none, so memory uses the server's key, if any. */
export interface ApiMemoryKey {
  provider: "openai" | "gemini" | null;
  keyHint: string | null;
  checkedAt: string | null;
}

/* ---------- Plugins ---------- */

/** A plugin the server loaded and its tools (GET /orgs/{id}/plugins). */
export interface ApiPlugin {
  id: string;
  name: string;
  version: string;
  description: string;
  tools: { name: string; title: string; description: string; risk: ApiRiskClass }[];
}

/* ---------- Connections (ADR 0010) ---------- */

type ApiTool = { name: string; title: string; description: string; risk: ApiRiskClass };

/** A plugin as Connect apps lists it (GET /orgs/{id}/connectors). */
/** An MCP server (GET /orgs/{id}/mcp-servers). Never carries its header key. */
export interface ApiMcpServer {
  id: string;
  pluginId: string;
  name: string;
  url: string;
  authKind: "none" | "header" | "oauth";
  authHeader: string | null;
  status: "active" | "unreachable" | "needs_sign_in" | "needs_reconnect";
  statusReason: string | null;
  tools: {
    name: string; serverName: string; title: string | null; description: string | null; annotations: Record<string, unknown>;
    inputSchema: Record<string, unknown>; outputSchema?: Record<string, unknown> | null; state: "approved" | "changed" | "pending" | "removed"; enabled: boolean;
    risk: "read" | "write-internal" | "write-external" | "external-send" | "destructive";
    previous: { title: string | null; description: string | null; inputSchema: Record<string, unknown> | null; outputSchema?: Record<string, unknown> | null } | null;
  }[];
  toolsHash: string;
  toolsChanged: number;
  lastCheckedAt: string | null;
  createdAt: string;
  createdBy: string | null;
  /** A data:image URI read from the server's handshake. Older APIs don't send it. */
  iconUrl?: string | null;
}

/** POST /orgs/{id}/mcp-servers: a server that wants a sign-in comes back with where to go. */
export type ApiMcpServerAdded = ApiMcpServer & { authorizeUrl: string | null };

export interface ApiMcpServerInput {
  name: string; url: string; apiKeyHeader?: string; apiKeyValue?: string; signIn?: boolean; oauthClientId?: string; oauthClientSecret?: string;
}

export interface ApiMcpToolChoice {
  serverName: string;
  enabled: boolean;
  risk: ApiMcpServer["tools"][number]["risk"];
}

export interface ApiConnector {
  id: string;
  name: string;
  description: string;
  version: string;
  authType: "oauth2" | "api_key" | null;
  setup: "ready" | "not-configured";
  accessLevels: string[];
  defaultAccess: string | null;
  tools: ApiTool[];
}

/** One authorised account (GET /orgs/{id}/connections). Never carries its credential. */
export interface ApiConnection {
  id: string;
  connectorId: string;
  ownerKind: "member" | "bot" | "org";
  ownerUserId: string | null;
  ownerBotId: string | null;
  authType: "oauth2" | "api_key";
  accountLabel: string;
  scopes: string[];
  status: "active" | "needs_reconnect" | "revoked";
  statusReason: string | null;
  createdAt: string;
  lastUsedAt: string | null;
  createdBy: string | null;
}

export interface ApiConnectionOwner {
  ownerKind: "member" | "bot" | "org";
  botId?: string;
}

/** A bot's tools (GET/PUT /orgs/{id}/bots/{bot}/tools). */
export interface ApiBotTools {
  plugins: {
    pluginId: string;
    name: string;
    description: string;
    authType: "oauth2" | "api_key" | null;
    enabled: boolean;
    connectionId: string | null;
    tools: ApiTool[];
    triggers?: { name: string; title: string; description: string; enabled: boolean; subscriberId: string | null; problem: string | null }[];
    /** MCP servers only (slice 7.4). */
    mcp?: { toolsWaiting: number; problem: string | null; orgAccount: boolean } | null;
  }[];
}

/* ---------- Routines ---------- */

/** A routine on the API: `instructions` say what to do; `cron` (5 fields) runs in `timezone` (IANA, its creator's). */
export interface ApiRoutine {
  id: string;
  botId: string | null;
  createdBy: string | null;
  name: string;
  /** Null for members who didn't create it: only its creator, owners and admins read it. */
  instructions: string | null;
  cron: string;
  timezone: string;
  enabled: boolean;
  securityLevel: ApiSecurityLevel | null;
  disabledReason: string | null;
  lastRunAt: string | null;
  nextRunAt: string | null;
  /** The latest run's status, or "skipped" (its previous run was still going, or a budget ran out). */
  lastResult: ApiRunStatus | "skipped" | null;
  createdAt: string;
}

export interface ApiRoutineInput {
  botId: string;
  name: string;
  instructions: string;
  cron: string;
  timezone: string;
  enabled: boolean;
}
