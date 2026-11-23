/**
 * Domain types for the BotDesk web UI.
 *
 * These mirror the data model in docs/architecture/high-level.md §8 and will move to
 * `packages/contract` once the API exists. Screens import types from here and data
 * from `@/data/store`, never from `@/data/mock`, so swapping the mock for the real
 * SDK touches one file.
 */

export type ID = string;
export type ISODate = string;

export type RiskClass =
  | "read"
  | "write-internal"
  | "write-external"
  | "external-send"
  | "spend"
  | "destructive"
  | "credential";

export type PolicyDecision = "auto" | "ask" | "deny";

export type SecurityLevel = "read-only" | "ask-before-acting" | "autonomous";

export interface User {
  id: ID;
  name: string;
  email: string;
  handle: string;
  avatarUrl?: string;
  role: "owner" | "admin" | "member";
  presence: "online" | "away" | "offline";
}

/** An invite to join the org that hasn't been accepted yet. Admins can revoke it. */
export interface Invitation {
  id: ID;
  email: string;
  role: "admin" | "member";
  createdAt: string;
  expiresAt: string;
}

export interface Org {
  id: ID;
  name: string;
  slug: string;
  /** The security level a new bot starts at (never above the ceiling). Owners and admins change it in Settings → Security. */
  defaultSecurityLevel: SecurityLevel;
  /** The ceiling: no bot here acts above this level, whatever its own (ADR 0004). "autonomous" = no ceiling. */
  maxSecurityLevel: SecurityLevel;
}

/** An organization you belong to, with your role in it: what the org switcher lists. */
export interface Membership extends Org {
  role: User["role"];
}

export type BotStatus = "idle" | "working" | "waiting-approval" | "sleeping" | "error";

export type BotAvatarColor =
  | "indigo"
  | "violet"
  | "sky"
  | "emerald"
  | "amber"
  | "rose"
  | "orange"
  | "slate";

export interface Bot {
  id: ID;
  name: string;
  handle: string;
  role: string;
  description: string;
  avatarColor: BotAvatarColor;
  isChief?: boolean;
  status: BotStatus;
  statusText?: string;
  modelId: ID;
  securityLevel: SecurityLevel;
  computerMode: "own" | "shared" | "none";
  connectionIds: ID[];
  instructions: string;
  createdAt: ISODate;
  /** What the bot may spend in a calendar month (UTC). 0 = no limit. */
  monthlyBudgetUsd: number;
  spentThisMonthUsd: number;
  /** Off: the bot neither recalls nor saves memories. What it already remembers stays until forgotten. */
  memoryEnabled: boolean;
}

export type ThreadKind = "dm" | "group";

export interface Participant {
  type: "user" | "bot";
  id: ID;
}

export interface Thread {
  id: ID;
  kind: ThreadKind;
  title: string;
  /** For DMs, the bot this thread is with. */
  botId?: ID;
  /** Groups: the bot that answers a message that @mentions no bot (ADR 0009). None: nobody does. */
  leadBotId?: ID;
  /** Who started the chat. A group's creator, owners and admins may change its lead. */
  createdBy?: ID;
  participants: Participant[];
  lastMessageAt: ISODate;
  lastMessagePreview: string;
  unread: number;
  pinned?: boolean;
}

/* ---------- Message parts (the cards inside a chat) ---------- */

export interface TextPart {
  type: "text";
  text: string;
}

export interface ReasoningPart {
  type: "reasoning";
  text: string;
  durationSec: number;
}

export interface WorkLogPart {
  type: "work-log";
  title: string;
  items: { label: string; detail?: string; done: boolean }[];
}

export interface ComputerTaskPart {
  type: "computer-task";
  title: string;
  app: string;
  status: "running" | "done" | "needs-takeover" | "failed";
  progress?: number;
  stepCount: number;
}

export interface ApprovalPart {
  type: "approval";
  approvalId: ID;
}

/**
 * A tool the bot used while replying: "Used Send email · done". Shown live from the run's
 * events, and saved in the reply (after the call's approval card, if it asked), so a
 * reloaded chat shows the same lines.
 */
export interface ToolCallPart {
  type: "tool-call";
  toolExecutionId: ID;
  /** Plugin id + tool name, like "demo.send_email". */
  tool: string;
  /** `unknown`: it failed after it may have been done (an email that may be out); its run waits for a person. */
  status: "running" | "succeeded" | "failed" | "denied" | "unknown";
  error?: string;
}

export interface QuestionPart {
  type: "question";
  question: string;
  options: string[];
  answered?: string;
}

export interface RoutineCreatedPart {
  type: "routine-created";
  routineId: ID;
  name: string;
}

export interface FilePart {
  type: "file";
  name: string;
  mime: string;
  sizeBytes: number;
}

/** Where a handed-off Task is (ADR 0014). `queued` and `working` are open; the rest are final. */
export type TaskStatus = "queued" | "working" | "done" | "failed" | "cancelled";

/**
 * One bot handing a Task to a teammate (`team.handoff`). The card lives in the handing-off
 * bot's message and changes in place as the Task moves on (`task_updated`).
 */
export interface HandoffPart {
  type: "handoff";
  taskId: ID;
  fromBotId: ID;
  toBotId: ID;
  task: string;
  status: TaskStatus;
  /** The owner's reply, once the Task is done: the card links to it. */
  resultMessageId?: ID;
  /** The first 280 characters of the result, whitespace collapsed. */
  resultPreview?: string;
  /** Why it failed or was cancelled. */
  error?: string;
  errorCode?: "budget" | "timeout" | "stopped";
}

export type MessagePart =
  | TextPart
  | ReasoningPart
  | WorkLogPart
  | ComputerTaskPart
  | ApprovalPart
  | ToolCallPart
  | QuestionPart
  | RoutineCreatedPart
  | FilePart
  | HandoffPart;

export interface Message {
  id: ID;
  threadId: ID;
  author: Participant | { type: "system"; id: "system" };
  parts: MessagePart[];
  createdAt: ISODate;
  mentions?: Participant[];
  status?: "streaming" | "complete" | "error";
  /** Why it failed, when `status` is "error": a reply that broke off, or a message that wasn't sent. */
  error?: string;
  /** "budget": the bot or the org reached its monthly budget, so the chat offers a way to raise it. */
  errorCode?: "budget";
  reactions?: { emoji: string; count: number }[];
}

/* ---------- Approvals ---------- */

export type ApprovalStatus = "pending" | "approved" | "edited" | "denied" | "expired";

/** The JSON Schema of a tool's arguments: enough of it to build an edit form. */
export interface ArgsSchema {
  type?: "object";
  properties?: Record<string, ArgSchema>;
  required?: string[];
}

export interface ArgSchema {
  type?: "string" | "number" | "integer" | "boolean";
  title?: string;
  description?: string;
  enum?: (string | number)[];
  format?: string;
  minLength?: number;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  default?: unknown;
  /** Optional arguments: `[{type: "string"}, {type: "null"}]`. */
  anyOf?: (ArgSchema | { type: "null" })[];
}

export interface Approval {
  id: ID;
  botId: ID;
  threadId: ID;
  /** The paused run. Mock approvals have none. */
  runId?: ID;
  riskClass: RiskClass;
  title: string;
  summary: string;
  /** Why the policy asked, e.g. "level=Ask before acting · risk=external-send · tainted=no → ask". */
  reason?: string;
  /** The run had read outside content (an email, a web page) before asking. */
  tainted?: boolean;
  /** The exact action, as label/value rows. */
  preview: { label: string; value: string }[];
  /** What the bot asked for, and the schema the Edit form is built from. */
  args?: Record<string, unknown>;
  argsSchema?: ArgsSchema | null;
  /** What was approved: the edited arguments after an edit. */
  finalArgs?: Record<string, unknown> | null;
  connectionId?: ID;
  status: ApprovalStatus;
  requestedAt: ISODate;
  expiresAt?: ISODate;
  decidedBy?: ID;
  /** The decider's name, for people the store doesn't know (say, someone who left). */
  decidedByName?: string;
  decidedAt?: ISODate;
}

/* ---------- Integrations (plugins) ---------- */

/** A tool a plugin on the server gives bots, with the risk that decides whether it asks first. */
export interface PluginTool {
  /** Full name, as on approval cards: "demo.send_email". */
  name: string;
  title: string;
  description: string;
  risk: RiskClass;
}

/** A plugin the API server loaded: built in, so there's nothing to connect. */
export interface Plugin {
  id: ID;
  name: string;
  version: string;
  description: string;
  tools: PluginTool[];
}

/** The server's plugins as last loaded. API only: the demo shows its mock connectors instead. */
export interface PluginList {
  status: "loading" | "ready" | "error";
  items: Plugin[];
}

/* ---------- Connections on the API (ADR 0010): connectors, accounts, each bot's tools ---------- */

/** How a connector's accounts are authorised. Null: it needs no account. */
export type AccountAuthType = "oauth2" | "api_key" | null;

/** A plugin as Connect apps lists it (GET /connectors). */
export interface ServerConnector {
  id: ID;
  name: string;
  description: string;
  version: string;
  authType: AccountAuthType;
  /** "not-configured": the server has no OAuth client for it yet (see the self-hosting guide). */
  setup: "ready" | "not-configured";
  /** OAuth access levels to choose between ("read", "full"); empty for the rest. */
  accessLevels: string[];
  defaultAccess: string | null;
  tools: PluginTool[];
}

/**
 * One tool of an MCP server, as its snapshot pinned it. `name` is BotDesk's ("mcp-1a2b3c4d.search_issues").
 * `state`: approved (offered when `enabled`), changed / pending (waits for an admin's review), removed.
 */
export interface McpTool {
  name: string;
  serverName: string;
  title: string | null;
  description: string | null;
  inputSchema: Record<string, unknown>;
  outputSchema: Record<string, unknown> | null;
  /** The server's own claims (readOnlyHint…): shown, never trusted. */
  annotations: Record<string, unknown>;
  state: "approved" | "changed" | "pending" | "removed";
  enabled: boolean;
  risk: McpToolRisk;
  /** For a changed tool: what an admin approved before (the drift diff compares it with now). */
  previous: McpToolDefinition | null;
}

/** The parts of an MCP tool its hash covers, as an admin last approved them. */
export interface McpToolDefinition {
  title: string | null;
  description: string | null;
  inputSchema: Record<string, unknown> | null;
  outputSchema: Record<string, unknown> | null;
}

/** The risks an admin may give an MCP tool on the review screen (never below read). */
export type McpToolRisk = "read" | "write-internal" | "write-external" | "external-send" | "destructive";

/** One tool's choice on the review screen. */
export interface McpToolChoice {
  serverName: string;
  enabled: boolean;
  risk: McpToolRisk;
}

/**
 * A remote MCP server an owner or admin added (ADR 0012). It is the plugin `pluginId`: bots get
 * its tools in their Tools tab. Its header key never comes back from the API.
 */
export interface McpServer {
  id: ID;
  pluginId: string;
  name: string;
  url: string;
  authKind: "none" | "header" | "oauth";
  authHeader: string | null;
  status: "active" | "unreachable" | "needs_sign_in" | "needs_reconnect";
  statusReason: string | null;
  tools: McpTool[];
  /** Sent back with the review, so a change in between isn't approved unseen. */
  toolsHash: string;
  /** Changed, new or removed tools waiting for the review ("Tools changed"). */
  toolsChanged: number;
  lastCheckedAt: string | null;
}

export interface McpServerList {
  status: "loading" | "ready" | "error";
  items: McpServer[];
}

/** Adding an MCP server: an API key (sent once in the named header), or OAuth sign-in with an optional pre-registered client. */
export interface McpServerInput {
  name: string;
  url: string;
  apiKeyHeader?: string;
  apiKeyValue?: string;
  signIn?: boolean;
  oauthClientId?: string;
  oauthClientSecret?: string;
}

export interface ServerConnectorList {
  status: "loading" | "ready" | "error";
  items: ServerConnector[];
}

/** Whose account a connection is. */
export type ConnectionOwnerKind = "member" | "bot" | "org";
export type ConnectionOwner = { kind: "member" } | { kind: "bot"; botId: ID } | { kind: "org" };

/** One authorised account on one connector. Never carries its credential. */
export interface AccountConnection {
  id: ID;
  connectorId: ID;
  ownerKind: ConnectionOwnerKind;
  ownerUserId: ID | null;
  ownerBotId: ID | null;
  authType: "oauth2" | "api_key";
  accountLabel: string;
  scopes: string[];
  status: "active" | "needs_reconnect" | "revoked";
  statusReason: string | null;
  createdAt: ISODate;
  lastUsedAt: ISODate | null;
}

export interface AccountConnectionList {
  status: "loading" | "ready" | "error";
  items: AccountConnection[];
}

/** One plugin in a bot's Tools tab: on or off, and the account it works through. */
export interface BotToolPlugin {
  pluginId: ID;
  name: string;
  description: string;
  authType: AccountAuthType;
  enabled: boolean;
  connectionId: ID | null;
  tools: PluginTool[];
  /** Things in the app the bot can react to ("React to new email"). API mode only. */
  triggers?: BotTrigger[];
  /** An MCP server's extras (API mode only; null for other plugins). */
  mcp?: BotToolMcp | null;
}

/** What a bot's Tools tab says about an MCP server besides the tools it offers (ADR 0012). */
export interface BotToolMcp {
  /** Changed or new tools no bot gets until an owner or admin approves them (Review tools). */
  toolsWaiting: number;
  /** Why its tools may not work now ("Needs signing in again: …"), or null. */
  problem: string | null;
  /** It uses the organization's key or sign-in, so only owners and admins switch it on or off. */
  orgAccount: boolean;
}

/** One of a plugin's triggers for this bot. When on, its events come to the DM of whoever switched it on. */
export interface BotTrigger {
  name: string;
  title: string;
  description: string;
  enabled: boolean;
  subscriberId: ID | null;
  /** Why the last check did nothing ("Paused: … needs reconnecting"), or null. */
  problem: string | null;
}

export interface BotTools {
  status: "loading" | "ready" | "error";
  plugins: BotToolPlugin[];
}

/** A change to one plugin of a bot (only the plugins sent change). */
export interface BotToolChange {
  pluginId: ID;
  enabled: boolean;
  connectionId: ID | null;
}

export interface ConnectorTool {
  name: string;
  description: string;
  risk: RiskClass;
}

/** What a plugin manifest declares. Gmail is the first; the shape scales to hundreds. */
export interface Connector {
  id: ID;
  name: string;
  publisher: string;
  category: "email" | "calendar" | "chat" | "dev" | "docs" | "crm" | "finance" | "mcp";
  description: string;
  authType: "oauth2" | "api-key" | "browser-login" | "none";
  tools: ConnectorTool[];
  triggers: string[];
  available: boolean;
}

export interface Connection {
  id: ID;
  connectorId: ID;
  account: string;
  owner: "user" | "org";
  status: "connected" | "expired" | "error";
  connectedAt: ISODate;
}

/* ---------- Routines, models, usage, memory ---------- */

export interface Routine {
  id: ID;
  /** Empty when its bot was removed (API): the routine stays, switched off, saying why. */
  botId: ID;
  name: string;
  /** What it does. On the API: the instructions the bot follows each time. */
  description: string;
  /** The schedule in words: "Weekdays at 7 AM". */
  schedule: string;
  source: "recording" | "chat" | "edit";
  /** The demo's step list. API routines have none: `description` says what to do. */
  steps: string[];
  lastRunAt?: ISODate;
  lastOutcome?: "success" | "failed" | "needs-approval" | "running" | "skipped";
  enabled: boolean;
  /* API only. */
  /** 5 fields (minute hour day month weekday), read in `timezone`. */
  cron?: string;
  /** IANA, e.g. "Asia/Karachi": its creator's when they saved it. */
  timezone?: string;
  nextRunAt?: ISODate;
  createdBy?: ID;
  /** Why BotDesk switched it off (its bot was removed, or its creator left). */
  disabledReason?: string;
  /** True when the API doesn't show you what it does (someone else's, and you're a member). */
  instructionsHidden?: boolean;
}

/** A model a bot can use, from a connected provider's live list. */
export interface Model {
  /** "provider:model", e.g. "anthropic:claude-opus-5-5" or "custom-<id>:llama3.2:latest". What a bot's modelId holds. */
  id: ID;
  /** The provider's id: "anthropic", "openai", "gemini", "openrouter", "groq" or "custom-<id>". */
  provider: string;
  name: string;
  contextWindow?: number;
  /** US dollars per million tokens, when the provider says (OpenRouter does). */
  pricing?: { inputPerMTok: number; outputPerMTok: number };
}

export type ModelProviderKind = "anthropic" | "openai" | "gemini" | "openrouter" | "groq" | "custom";

/** A model provider and whether the org has a key for it (Settings → Models & keys). The key itself never reaches the browser. */
export interface ModelProvider {
  /** The kind for built-in providers; "custom-<id>" for an OpenAI-compatible server. */
  id: ID;
  kind: ModelProviderKind;
  /** The provider's name, or what people called their custom server. */
  name: string;
  hint: string;
  connected: boolean;
  /** "org": the org's key, saved in Settings. "member": your own key (My keys). "env": a key set on the server, for everyone on it. */
  source?: "org" | "member" | "env";
  /** The key's last 4 characters. */
  keyHint?: string;
  /** How the key's last check went. */
  status?: "ok" | "invalid";
  lastVerifiedAt?: ISODate;
  baseUrl?: string;
}

/** A connected provider whose model list couldn't be fetched just now. */
export interface ModelListProblem {
  provider: string;
  message: string;
}

/**
 * Whose memory it is. "bot": learned in group chats, so the bot uses it in everyone's chats.
 * "you": learned in your DM with the bot, and used only there. Nobody sees another member's.
 */
export type MemoryScope = "bot" | "you";

/** Something a bot remembers (Settings → Memory, and the Memory tab in a bot's details). */
export interface MemoryItem {
  id: ID;
  botId: ID;
  text: string;
  scope: MemoryScope;
  createdAt?: ISODate;
  /** Set when someone corrected it after it was saved. */
  updatedAt?: ISODate;
}

/** Whether bots can remember on this server; when they can't, `reason` says what to set. */
export interface MemoryStatus {
  enabled: boolean;
  reason?: string;
}

/** One bot's memories as last loaded: all of them, or the matches for `query`. */
export interface MemoryList {
  status: "loading" | "ready" | "error";
  query: string;
  items: MemoryItem[];
  error?: string;
}

/* ---------- Files and storage (ADR 0017) ---------- */

/** Where the organization keeps bots' files: on the BotDesk server (Local) or its own S3-compatible bucket. */
export type StorageProviderId = "local" | "s3";

/** An S3-compatible bucket as the API shows it: never the keys, only the access key's last 4 characters. */
export interface S3Storage {
  /** Empty for AWS itself. */
  endpoint: string;
  region: string;
  bucket: string;
  /** A folder inside the bucket; empty for its top. */
  prefix: string;
  accessKeyHint: string;
}

/** The organization's file storage (Settings → Computers). */
export interface FileStorage {
  provider: StorageProviderId;
  s3?: S3Storage;
  /** Whether this server lets organizations keep files on its own disk (the operator can turn Local off). */
  localAvailable: boolean;
  /** When the S3 bucket last passed its check. */
  checkedAt?: ISODate;
}

/** The organization's storage as last loaded. */
export interface StorageLoad {
  status: "loading" | "ready" | "error";
  current?: FileStorage;
}

/** A file in a bot's folder (no `botId`: the shared folder every bot can read). */
export interface BotFile {
  id: ID;
  botId?: ID;
  /** Inside the folder: "reports/march.csv". */
  path: string;
  /** "botdesk/inbox-manager", or "botdesk/_shared". */
  folder: string;
  contentType: string;
  sizeBytes: number;
  /** False when it was saved to storage the organization no longer uses: listed, but it can't be opened. */
  available: boolean;
  createdAt: ISODate;
  updatedAt: ISODate;
  /** Where the browser opens it. Empty when there's nothing to open (a demo file in tests). */
  url: string;
}

/** One bot's files as last loaded. */
export interface BotFileList {
  status: "loading" | "ready" | "error";
  items: BotFile[];
  error?: string;
}

/** One UTC day of spend. Token counts come from the API; the demo has dollars only. */
export interface UsageDay {
  date: ISODate;
  tokensUsd: number;
  computerUsd: number;
  inputTokens?: number;
  outputTokens?: number;
  /** Tokens from models with no known price (custom servers, models missing from the price table). */
  unpricedTokens?: number;
}

/** Settings → Usage & budgets. Each bot's own spend is on the bot (`spentThisMonthUsd`). */
export interface UsageSummary {
  /** Oldest first, one per day. */
  days: UsageDay[];
  monthToDateUsd: number;
  /** Tokens this month whose price isn't known, so they aren't in the dollar totals. */
  unpricedTokens: number;
  /** What all the org's bots together may spend this month. Unset = no limit. */
  orgBudgetUsd?: number;
}

/**
 * A ready-made bot in the marketplace. On the API the catalogue comes from `GET /templates`
 * (`apps/api/src/templates/catalogue.json`); the demo shows the same templates.
 */
export interface Template {
  id: ID;
  name: string;
  role: string;
  category: string;
  description: string;
  /** What the hired bot is told to do. */
  instructions: string;
  avatarColor: BotAvatarColor;
  /** How careful the job needs it to be: a hired bot starts here or at the org's default, whichever is stricter. */
  securityLevel: SecurityLevel;
  /** The plugins it works in, by id ("gmail"); hiring switches them on in its Tools. On the API, only ones the server loaded. */
  plugins: ID[];
  /** DEMO: how many teams hired it. The API doesn't count, so it's left out there. */
  installs?: number;
}

export interface TemplateList {
  status: "loading" | "ready" | "error";
  items: Template[];
}
