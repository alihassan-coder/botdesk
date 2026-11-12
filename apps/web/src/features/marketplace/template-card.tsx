import { Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatCount } from "@/lib/format";
import type { Template } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";

/** One ready-made bot: who it is, what it does, how popular, which apps it uses, and Hire. */
export function TemplateCard({ template, onHire }: { template: Template; onHire: () => void }) {
  return (
    <article className="group flex flex-col gap-4 rounded-2xl border bg-card p-5 transition-shadow hover:shadow-md">
      <div className="flex items-start gap-3">
        <BotAvatar name={template.name} color={template.avatarColor} size="lg" />
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-semibold tracking-tight">{template.name}</h3>
          <p className="text-sm text-muted-foreground">{template.role}</p>
        </div>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{template.category}</span>
      </div>

      <p className="flex-1 text-sm leading-relaxed">{template.description}</p>

      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span>{formatCount(template.installs)} hires</span>
        {template.connectors.includes("gmail") && (
          <span className="flex items-center gap-1">
            <Mail className="size-3.5" /> Gmail
          </span>
        )}
        <Button size="sm" className="ml-auto" onClick={onHire} aria-label={`Hire ${template.name}`}>
          Hire
        </Button>
      </div>
    </article>
  );
}
