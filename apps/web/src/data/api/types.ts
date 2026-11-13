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

export type ApiSecurityLevel = "read-only" | "ask-before-acting" | "autonomous";

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
  status: "idle" | "working" | "waiting-approval" | "sleeping" | "error";
  createdAt: string;
}

/** What you send to hire or edit a bot; the API fills in id, handle, status and createdAt. */
export type ApiBotInput = Pick<
  ApiBot,
  "name" | "role" | "description" | "instructions" | "avatarColor" | "modelId" | "securityLevel" | "monthlyBudgetUsd"
>;

/* ---------- Models & keys ---------- */

export interface ApiModelProvider {
  id: string;
  kind: "anthropic" | "openai" | "gemini" | "openrouter" | "groq" | "custom";
  name: string;
  hint: string;
  connected: boolean;
  source: "org" | "env" | null;
  keyHint: string | null;
  status: "ok" | "invalid" | null;
  lastVerifiedAt: string | null;
  baseUrl: string | null;
}

/** Add or replace a key. Custom servers also send a base URL and a name; their key may be "". */
export interface ApiProviderKeyInput {
  apiKey: string;
  baseUrl?: string;
  label?: string;
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
  participants: { type: "user" | "bot"; id: string }[];
  lastMessageAt: string;
  /** "" until the chat has a message. */
  lastMessagePreview: string;
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
  | { kind: "run_failed"; data: { status: "failed"; error: string } }
  | { kind: "tool_started"; data: { toolExecutionId: string; tool: string; risk: ApiRiskClass; args: Record<string, unknown> } }
  | {
      kind: "tool_finished";
      data: { toolExecutionId: string; tool: string; status: "succeeded" | "failed" | "denied"; result: unknown; error: string | null };
    }
  | { kind: "approval_requested"; data: { approval: ApiApproval } }
  | { kind: "approval_decided"; data: { approval: ApiApproval } }
  | { kind: "run_resumed"; data: { botId: string } }
  | { kind: "run_needs_attention"; data: { status: "needs_attention"; error: string } }
);

export const RUN_EVENT_KINDS = [
  "message_saved", "run_started", "message_delta", "run_finished", "run_failed",
  "tool_started", "tool_finished", "approval_requested", "approval_decided", "run_resumed", "run_needs_attention",
] as const satisfies readonly ApiRunEvent["kind"][];
