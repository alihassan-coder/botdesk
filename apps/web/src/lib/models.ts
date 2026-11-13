import type { Model, ModelProvider } from "@/data/types";
import { formatCount } from "./format";

/** One provider's models, in the order the provider gave them. */
export interface ModelGroup {
  providerId: string;
  providerName: string;
  models: Model[];
}

/** True when the query's words all appear in the model's name, id or provider name. */
export function modelMatches(model: Model, query: string, providerName = ""): boolean {
  const haystack = `${model.name} ${model.id} ${providerName}`.toLowerCase();
  return query.toLowerCase().split(/\s+/).filter(Boolean).every((word) => haystack.includes(word));
}

/**
 * Models grouped by provider, in the order providers are listed (built-ins first, then custom
 * servers), keeping only those that match `query`. Providers with no matching models are left out.
 */
export function groupModels(models: Model[], providers: ModelProvider[], query = ""): ModelGroup[] {
  const names = new Map(providers.map((p) => [p.id, p.name]));
  const order = [...providers.map((p) => p.id), ...models.map((m) => m.provider)];
  const groups = new Map<string, ModelGroup>();
  for (const providerId of order) {
    if (!groups.has(providerId)) groups.set(providerId, { providerId, providerName: names.get(providerId) ?? providerId, models: [] });
  }
  for (const model of models) {
    const group = groups.get(model.provider)!;
    if (modelMatches(model, query, group.providerName)) group.models.push(model);
  }
  return [...groups.values()].filter((g) => g.models.length > 0);
}

/** "$3 / $15 per M tokens", or undefined when the provider doesn't publish prices. */
export function formatModelPrice(model: Model): string | undefined {
  if (!model.pricing) return undefined;
  const { inputPerMTok, outputPerMTok } = model.pricing;
  if (inputPerMTok === 0 && outputPerMTok === 0) return "Free";
  const usd = (n: number) => `$${Number(n.toFixed(2))}`;
  return `${usd(inputPerMTok)} / ${usd(outputPerMTok)} per M tokens`;
}

/** "1M context", or undefined when unknown. */
export function formatContextWindow(model: Model): string | undefined {
  return model.contextWindow ? `${formatCount(model.contextWindow)} context` : undefined;
}

/** "••••1234", or "No key shown" for keys too short (or absent, like Ollama) to show any of. */
export function maskedKey(keyHint?: string): string {
  return keyHint ? `••••${keyHint}` : "No key shown";
}
