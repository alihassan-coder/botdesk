import { ConnectorLogo } from "@/components/connector-logo";
import { Button } from "@/components/ui/button";
import { formatCount } from "@/lib/format";
import type { Template } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";

/**
 * One ready-made bot: who it is, what it does, and Hire. The demo also shows how popular it is
 * and which apps it uses; on the API those would be made up (no hire counts, no app connections yet).
 */
export function TemplateCard({ template, onHire, demo }: { template: Template; onHire: () => void; demo: boolean }) {
  return (
    <article className="group flex flex-col gap-4 rounded-2xl border bg-card p-5 transition-shadow hover:shadow-md">
      <div className="flex items-start gap-3">
        <BotAvatar name={template.name} color={template.avatarColor} size="lg" />
        {/* The category sits under the role, not beside the name, so a narrow card keeps the whole name. */}
        <div className="flex min-w-0 flex-1 flex-col items-start gap-1">
          <h3 className="max-w-full truncate font-semibold tracking-tight">{template.name}</h3>
          <p className="text-sm text-muted-foreground">{template.role}</p>
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{template.category}</span>
        </div>
      </div>

      <p className="flex-1 text-sm leading-relaxed">{template.description}</p>

      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        {demo && <span>{formatCount(template.installs)} hires</span>}
        {demo && template.connectors.includes("gmail") && (
          <span className="flex items-center gap-1">
            <ConnectorLogo connectorId="gmail" name="Gmail" size="xs" decorative /> Gmail
          </span>
        )}
        <Button size="sm" className="ml-auto" onClick={onHire} aria-label={`Hire ${template.name}`}>
          Hire
        </Button>
      </div>
    </article>
  );
}
