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
  plan: "self-hosted" | "free" | "pro" | "team";
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
  status: "running" | "succeeded" | "failed" | "denied";
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

export interface HandoffPart {
  type: "handoff";
  fromBotId: ID;
  toBotId: ID;
  task: string;
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
  botId: ID;
  name: string;
  description: string;
  schedule: string;
  source: "recording" | "chat" | "edit";
  steps: string[];
  lastRunAt?: ISODate;
  lastOutcome?: "success" | "failed" | "needs-approval";
  enabled: boolean;
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
  /** "org": a key saved in Settings. "env": a key set on the server, for everyone on it. */
  source?: "org" | "env";
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

export interface Template {
  id: ID;
  name: string;
  role: string;
  description: string;
  avatarColor: BotAvatarColor;
  installs: number;
  connectors: ID[];
  category: string;
}
