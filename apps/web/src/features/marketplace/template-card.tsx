import { ConnectorLogo } from "@/components/connector-logo";
import { Button } from "@/components/ui/button";
import { formatCount } from "@/lib/format";
import { strictestLevel } from "@/lib/security-level";
import { useConnectors, useOrg } from "@/data/store";
import type { Template } from "@/data/types";
import { BotAvatar } from "@/features/bots/bot-avatar";
import { securityLabel } from "@/features/bots/security-levels";

/**
 * One ready-made bot: who it is, what it does, the apps it works in, and Hire. A template that
 * needs more care than your organization's default says the level its bot starts at. The demo
 * also shows how popular it is; the API counts no hires, so there it would be made up.
 */
export function TemplateCard({
  template,
  onHire,
  demo,
  hiring = false,
  disabled = false,
}: {
  template: Template;
  onHire: () => void;
  demo: boolean;
  hiring?: boolean;
  disabled?: boolean;
}) {
  const connectors = useConnectors();
  const orgDefault = useOrg().defaultSecurityLevel;
  const startsAt = strictestLevel(template.securityLevel, orgDefault);
  const apps = template.plugins.map((id) => ({ id, name: connectors.find((c) => c.id === id)?.name ?? id }));

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

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted-foreground">
        {demo && template.installs !== undefined && <span>{formatCount(template.installs)} hires</span>}
        {apps.map((app) => (
          <span key={app.id} className="flex items-center gap-1">
            <ConnectorLogo connectorId={app.id} name={app.name} size="xs" decorative /> {app.name}
          </span>
        ))}
        {startsAt !== orgDefault && <span>Starts at {securityLabel(startsAt)}</span>}
        <Button size="sm" className="ml-auto" onClick={onHire} disabled={disabled} aria-label={`Hire ${template.name}`}>
          {hiring ? "Hiring…" : "Hire"}
        </Button>
      </div>
    </article>
  );
}
