import { Brain, Gem, Route, Server, Sparkles, Zap, type LucideIcon } from "lucide-react";
import type { ModelProviderKind } from "@/data/types";

/* Generic icons, not the providers' logos: BotDesk ships no third-party brand assets. */
const ICONS: Record<ModelProviderKind, LucideIcon> = {
  anthropic: Sparkles,
  openai: Brain,
  gemini: Gem,
  openrouter: Route,
  groq: Zap,
  custom: Server,
};

export function ProviderIcon({ kind }: { kind: ModelProviderKind }) {
  const Icon = ICONS[kind];
  return (
    <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-muted" aria-hidden>
      <Icon className="size-4 text-muted-foreground" />
    </span>
  );
}
