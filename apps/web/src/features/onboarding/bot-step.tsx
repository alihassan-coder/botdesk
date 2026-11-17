import { useState } from "react";
import Link from "next/link";
import { Check } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { actions, useTemplates } from "@/data/store";
import type { Template } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { cn } from "@/lib/utils";
import { StepFrame } from "./step-frame";

/* Chief first: a chief of staff hands work to the bots you hire later (ADR 0014). */
const RECOMMENDED = ["tpl_chief", "tpl_inbox"];

/**
 * Step 3: hire a first bot from the marketplace (same action as its Hire button), or leave
 * setup to build one from scratch. `onHired` gets the new bot's DM, which Finish opens.
 */
export function BotStep({ onNext, onHired, onLeave }: { onNext: () => void; onHired: (threadId: string) => void; onLeave: () => void }) {
  const templates = useTemplates();
  const picks = RECOMMENDED.map((id) => templates.find((t) => t.id === id)).filter((t): t is Template => t !== undefined);
  const [hired, setHired] = useState<string[]>([]);
  const [hiring, setHiring] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function hire(t: Template) {
    setHiring(t.id);
    setError("");
    const result = await actions.createBotFromTemplate(t.id);
    setHiring(null);
    if (!result.ok) return setError(result.error);
    setHired((h) => [...h, t.id]);
    if (result.threadId) onHired(result.threadId);
  }

  return (
    <StepFrame
      title="Hire your first bot"
      description="Start with Chief, your chief of staff: tell it what you need and it plans the work and hands tasks to the rest of the team."
      onSkip={onNext}
      action={<Button onClick={onNext} disabled={hired.length === 0}>Continue</Button>}
    >
      {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
      <ul className="grid gap-3">
        {picks.map((t, i) => (
          <li key={t.id} className={cn("flex items-start gap-4 rounded-2xl border p-4", i === 0 && "border-brand/40 bg-brand/5")}>
            <BotAvatar name={t.name} color={t.avatarColor} size={i === 0 ? "lg" : "md"} />
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-2 font-medium">
                {t.name}
                {i === 0 && <Badge>Recommended</Badge>}
              </p>
              <p className="text-sm text-muted-foreground">{t.role}</p>
              <p className="mt-1 text-sm text-pretty">{t.description}</p>
            </div>
            {hired.includes(t.id) ? (
              <span className="flex shrink-0 items-center gap-1 text-sm font-medium" role="status"><Check className="size-4" /> Hired</span>
            ) : (
              <Button size="sm" className="shrink-0" variant={i === 0 ? "default" : "outline"} disabled={hiring !== null} onClick={() => void hire(t)} aria-label={`Hire ${t.name}`}>
                {hiring === t.id ? "Hiring…" : "Hire"}
              </Button>
            )}
          </li>
        ))}
      </ul>
      <p className="text-sm text-muted-foreground">
        Want something else?{" "}
        <Link href="/bots/new" onClick={onLeave} className="tap-target font-medium text-foreground underline underline-offset-4">Create one from scratch</Link>
        {" "}or{" "}
        <Link href="/marketplace" onClick={onLeave} className="tap-target font-medium text-foreground underline underline-offset-4">browse the marketplace</Link>.
      </p>
    </StepFrame>
  );
}
