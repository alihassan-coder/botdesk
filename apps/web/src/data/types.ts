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
  monthlyBudgetUsd: number;
  spentThisMonthUsd: number;
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
  reactions?: { emoji: string; count: number }[];
}

/* ---------- Approvals ---------- */

export type ApprovalStatus = "pending" | "approved" | "denied" | "expired";

export interface Approval {
  id: ID;
  botId: ID;
  threadId: ID;
  riskClass: RiskClass;
  title: string;
  summary: string;
  /** The exact action, shown as a preview the human can edit before approving. */
  preview: { label: string; value: string }[];
  connectionId?: ID;
  status: ApprovalStatus;
  requestedAt: ISODate;
  decidedBy?: ID;
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

export interface Model {
  id: ID;
  provider: string;
  name: string;
  capabilities: ("vision" | "tools" | "reasoning" | "computer-use")[];
  priceInPerMTok: number;
  priceOutPerMTok: number;
  contextWindow: number;
}

export interface ProviderCredential {
  id: ID;
  provider: string;
  label: string;
  owner: "user" | "org";
  baseUrl?: string;
  lastUsedAt?: ISODate;
  maskedKey: string;
}

export interface MemoryItem {
  id: ID;
  botId?: ID;
  text: string;
  source: string;
  createdAt: ISODate;
}

export interface UsageDay {
  date: ISODate;
  tokensUsd: number;
  computerUsd: number;
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
