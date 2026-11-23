import type { BrowserProvider, BrowserProviderId } from "@/data/types";

/** A cloud browser provider in Settings → Computers: what it is in one line, and its pricing page (prices change, so BotDesk links). */
export interface CloudBrowserInfo {
  id: Exclude<BrowserProviderId, "local">;
  name: string;
  hint: string;
  pricingUrl: string;
}

export const CLOUD_BROWSERS: CloudBrowserInfo[] = [
  { id: "steel", name: "Steel", hint: "Open source; free credits to start.", pricingUrl: "https://steel.dev/pricing" },
  { id: "browserbase", name: "Browserbase", hint: "Free plan: 1 browser hour a month.", pricingUrl: "https://www.browserbase.com/pricing" },
  { id: "kernel", name: "Kernel", hint: "Free monthly credits.", pricingUrl: "https://www.kernel.sh/pricing" },
];

/** "Local", "Steel", "Browserbase", "Kernel". */
export function browserProviderName(id: BrowserProviderId): string {
  return id === "local" ? "Local" : CLOUD_BROWSERS.find((p) => p.id === id)?.name ?? id;
}

/** The API takes keys of at least this many characters. */
const MIN_KEY = 8;

/**
 * What's wrong with the key before the API is asked (it checks the rest by starting a browser).
 * An empty key keeps the saved one, but only for the provider that's already chosen.
 */
export function browserKeyProblem(provider: BrowserProviderId, apiKey: string, saved?: BrowserProvider): string | undefined {
  if (provider === "local") return undefined;
  const key = apiKey.trim();
  if (!key) return saved?.provider === provider && saved.keyHint ? undefined : `Paste your ${browserProviderName(provider)} API key.`;
  return key.length < MIN_KEY ? "That key looks too short. Paste the whole key." : undefined;
}
