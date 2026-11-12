import type { Bot, Invitation, Message, MessagePart, Org, Thread, User } from "../types";
import type { ApiBot, ApiBotInput, ApiInvitation, ApiMessage, ApiOrg, ApiRole, ApiThread, ApiUser } from "./types";

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

/*
 * The model list is still mock data with short ids ("m_claude"); the API stores
 * "provider:model". This table translates until the model list comes from the API.
 */
const API_MODEL_ID: Record<string, string> = {
  m_claude: "anthropic:claude-sonnet-5.5",
  m_gpt: "openai:gpt-5.5",
  m_grok: "xai:grok-4.5",
  m_gemini: "google:gemini-3-pro",
  m_deepseek: "deepseek:deepseek-v4",
  m_llama: "ollama:llama-4-scout",
};
const WEB_MODEL_ID = Object.fromEntries(Object.entries(API_MODEL_ID).map(([web, api]) => [api, web]));

/** Bots on the API don't have computers, connections or spend yet, so those start empty. */
export function toBot({ modelId, createdAt, ...bot }: ApiBot): Bot {
  return { ...bot, createdAt: asUtc(createdAt), modelId: WEB_MODEL_ID[modelId] ?? modelId, computerMode: "none", connectionIds: [], spentThisMonthUsd: 0 };
}

/** The fields of a bot the API stores, ready to send. Anything else (computer, status…) stays behind. */
export function toApiBot(bot: Partial<Bot>): Partial<ApiBotInput> {
  const fields: Partial<ApiBotInput> = {};
  for (const key of ["name", "role", "description", "instructions", "avatarColor", "securityLevel"] as const) {
    if (bot[key] !== undefined) Object.assign(fields, { [key]: bot[key] });
  }
  if (bot.modelId !== undefined) fields.modelId = API_MODEL_ID[bot.modelId] ?? bot.modelId;
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
  "text", "reasoning", "work-log", "computer-task", "approval", "question", "routine-created", "file", "handoff",
]);

export function toMessage({ id, threadId, author, parts, status, createdAt }: ApiMessage): Message {
  return {
    id, threadId, status, createdAt: asUtc(createdAt),
    author: author.type === "system" || !author.id ? { type: "system", id: "system" } : { type: author.type, id: author.id },
    parts: parts.filter((part) => KNOWN_PARTS.has(part.type as MessagePart["type"])) as unknown as MessagePart[],
  };
}
