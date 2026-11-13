import type { Approval, ArgsSchema, Bot, Invitation, MemoryItem, MemoryStatus, Message, MessagePart, Model, ModelProvider, Org, Thread, UsageSummary, User } from "../types";
import type { ApiApproval, ApiBot, ApiBotInput, ApiInvitation, ApiMemory, ApiMemoryStatus, ApiMessage, ApiModel, ApiModelProvider, ApiOrg, ApiRole, ApiThread, ApiUsage, ApiUser } from "./types";

/**
 * Turns API answers into the web app's own types, so screens never see API shapes.
 * A person's role belongs to their membership in an org, so it's passed in.
 * The API has no presence yet, so everyone shows as online.
 */
/**
 * API times are UTC. On SQLite (local dev) they come back without the "Z", which the browser
 * would read as local time, so a chat started just now said "5h". Add the "Z" when it's missing.
 */
export function asUtc(iso: string): string {
  return /(Z|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`;
}

export function toUser({ id, name, email, handle }: ApiUser, role: ApiRole): User {
  return { id, name, email, handle, role, presence: "online" };
}

export function toOrg({ id, name, slug, plan }: ApiOrg): Org {
  return { id, name, slug, plan };
}

/** Drops the one-time invite link, so it never sits in the store. */
export function toInvitation({ id, email, role, createdAt, expiresAt }: ApiInvitation): Invitation {
  return { id, email, role, createdAt: asUtc(createdAt), expiresAt: asUtc(expiresAt) };
}

/** Bots on the API don't have computers or connections yet. Spend comes from the usage report (toUsage). */
export function toBot({ createdAt, ...bot }: ApiBot): Bot {
  return { ...bot, createdAt: asUtc(createdAt), computerMode: "none", connectionIds: [], spentThisMonthUsd: 0 };
}

/** The fields of a bot the API stores, ready to send. Anything else (computer, status…) stays behind. */
export function toApiBot(bot: Partial<Bot>): Partial<ApiBotInput> {
  const fields: Partial<ApiBotInput> = {};
  for (const key of ["name", "role", "description", "instructions", "avatarColor", "modelId", "securityLevel", "memoryEnabled"] as const) {
    if (bot[key] !== undefined) Object.assign(fields, { [key]: bot[key] });
  }
  if (bot.monthlyBudgetUsd !== undefined) fields.monthlyBudgetUsd = Math.round(bot.monthlyBudgetUsd);
  return fields;
}

/** The API doesn't count unread messages yet, so every chat starts read. */
export function toThread({ id, kind, title, botId, participants, lastMessageAt, lastMessagePreview }: ApiThread): Thread {
  return {
    id, kind, title, participants, lastMessagePreview, lastMessageAt: asUtc(lastMessageAt), unread: 0,
    ...(botId ? { botId } : {}),
  };
}

/* The part types the web app can show. Bots may send others later; those are left out until it can. */
const KNOWN_PARTS = new Set<MessagePart["type"]>([
  "text", "reasoning", "work-log", "computer-task", "approval", "tool-call", "question", "routine-created", "file", "handoff",
]);

export function toMessage({ id, threadId, author, parts, status, createdAt }: ApiMessage): Message {
  return {
    id, threadId, status, createdAt: asUtc(createdAt),
    author: author.type === "system" || !author.id ? { type: "system", id: "system" } : { type: author.type, id: author.id },
    parts: parts.filter((part) => KNOWN_PARTS.has(part.type as MessagePart["type"])) as unknown as MessagePart[],
  };
}

/** The decider comes with a name, so the card can say who even if they've left the org. */
export function toApproval(a: ApiApproval): Approval {
  return {
    id: a.id, botId: a.botId, threadId: a.threadId, runId: a.runId,
    riskClass: a.riskClass, title: a.title, summary: a.summary, reason: a.reason, tainted: a.tainted,
    preview: a.preview, args: a.args, finalArgs: a.finalArgs, argsSchema: a.argsSchema as ArgsSchema | null,
    status: a.status, requestedAt: asUtc(a.requestedAt), expiresAt: asUtc(a.expiresAt),
    ...(a.decidedAt ? { decidedAt: asUtc(a.decidedAt) } : {}),
    ...(a.decidedBy ? { decidedBy: a.decidedBy.id, decidedByName: a.decidedBy.name } : {}),
  };
}

/* ---------- Usage and budgets ---------- */

/** The usage report as the web app keeps it: the summary, plus each bot's spend by bot id. A budget of null is no limit. */
export function toUsage(usage: ApiUsage): { summary: UsageSummary; spentByBot: Record<string, number> } {
  return {
    summary: {
      days: usage.days.map((d) => ({
        date: d.date, tokensUsd: d.modelsUsd, computerUsd: d.computersUsd,
        inputTokens: d.inputTokens, outputTokens: d.outputTokens, unpricedTokens: d.unpricedTokens,
      })),
      monthToDateUsd: usage.monthToDateUsd,
      unpricedTokens: usage.unpricedTokens,
      ...(usage.orgBudgetUsd ? { orgBudgetUsd: usage.orgBudgetUsd } : {}),
    },
    spentByBot: Object.fromEntries(usage.bots.map((b) => [b.botId, b.spentUsd])),
  };
}

/* ---------- Models & keys ---------- */

/** The API sends null for "not known"; the web app leaves those fields out. */
export function toModelProvider({ source, keyHint, status, lastVerifiedAt, baseUrl, ...provider }: ApiModelProvider): ModelProvider {
  return {
    ...provider,
    ...(source ? { source } : {}),
    ...(keyHint ? { keyHint } : {}),
    ...(status ? { status } : {}),
    ...(lastVerifiedAt ? { lastVerifiedAt: asUtc(lastVerifiedAt) } : {}),
    ...(baseUrl ? { baseUrl } : {}),
  };
}

export function toModel({ id, provider, name, contextWindow, pricing }: ApiModel): Model {
  return {
    id, provider, name,
    ...(contextWindow ? { contextWindow } : {}),
    ...(pricing ? { pricing: { inputPerMTok: pricing.inputPerMtok, outputPerMTok: pricing.outputPerMtok } } : {}),
  };
}

/* ---------- Memory ---------- */

/** The API doesn't say which bot a memory belongs to (it's in the URL), so it's passed in. */
export function toMemory({ id, text, scope, createdAt, updatedAt }: ApiMemory, botId: string): MemoryItem {
  return {
    id, botId, text, scope,
    ...(createdAt ? { createdAt: asUtc(createdAt) } : {}),
    ...(updatedAt && updatedAt !== createdAt ? { updatedAt: asUtc(updatedAt) } : {}),
  };
}

export function toMemoryStatus({ enabled, reason }: ApiMemoryStatus): MemoryStatus {
  return { enabled, ...(reason ? { reason } : {}) };
}
