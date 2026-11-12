import type { Bot, Invitation, Org, User } from "../types";
import type { ApiBot, ApiBotInput, ApiInvitation, ApiOrg, ApiRole, ApiUser } from "./types";

/**
 * Turns API answers into the web app's own types, so screens never see API shapes.
 * A person's role belongs to their membership in an org, so it's passed in.
 * The API has no presence yet, so everyone shows as online.
 */
export function toUser({ id, name, email, handle }: ApiUser, role: ApiRole): User {
  return { id, name, email, handle, role, presence: "online" };
}

export function toOrg({ id, name, slug, plan }: ApiOrg): Org {
  return { id, name, slug, plan };
}

/** Drops the one-time invite link, so it never sits in the store. */
export function toInvitation({ id, email, role, createdAt, expiresAt }: ApiInvitation): Invitation {
  return { id, email, role, createdAt, expiresAt };
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
export function toBot({ modelId, ...bot }: ApiBot): Bot {
  return { ...bot, modelId: WEB_MODEL_ID[modelId] ?? modelId, computerMode: "none", connectionIds: [], spentThisMonthUsd: 0 };
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
