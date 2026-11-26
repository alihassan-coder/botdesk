import type { MemoryKeyProvider } from "@/data/types";

/** A provider whose key memory can use (Settings → Memory), with where to get a key in one line. */
export interface MemoryKeyProviderInfo {
  id: MemoryKeyProvider;
  name: string;
  hint: string;
}

export const MEMORY_KEY_PROVIDERS: MemoryKeyProviderInfo[] = [
  { id: "openai", name: "OpenAI", hint: "An API key from platform.openai.com." },
  { id: "gemini", name: "Google Gemini", hint: "An API key from Google AI Studio (aistudio.google.com)." },
];

/** "OpenAI", "Google Gemini". */
export function memoryKeyProviderName(id: MemoryKeyProvider): string {
  return MEMORY_KEY_PROVIDERS.find((p) => p.id === id)?.name ?? id;
}

/** The API takes keys of 8 to 400 characters. */
const MIN_KEY = 8;
const MAX_KEY = 400;

/** What's wrong with the key before the API is asked (it checks the rest with the provider). There's always one to paste. */
export function memoryKeyProblem(provider: MemoryKeyProvider, apiKey: string): string | undefined {
  const key = apiKey.trim();
  if (!key) return `Paste your ${memoryKeyProviderName(provider)} API key.`;
  if (key.length < MIN_KEY) return "That key looks too short. Paste the whole key.";
  return key.length > MAX_KEY ? "That's too long for an API key. Paste only the key." : undefined;
}
