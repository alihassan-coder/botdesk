import { ShieldAlert, ShieldCheck, ShieldEllipsis } from "lucide-react";
import { Field, FieldContent, FieldDescription, FieldLabel, FieldTitle } from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { SecurityLevel } from "@/data/types";
import { looserThan } from "@/lib/security-ceiling";
import { SECURITY_LEVELS, securityLabel } from "./security-levels";

const ICON = { "read-only": ShieldCheck, "ask-before-acting": ShieldEllipsis, autonomous: ShieldAlert };

interface SecurityLevelPickerProps {
  value: SecurityLevel;
  onChange: (level: SecurityLevel) => void;
  disabled?: boolean;
  /** The organization's ceiling: levels above it can't be picked (ADR 0004). Leave out for no limit. */
  max?: SecurityLevel;
  /** Names the group, and keeps ids unique when a page has two pickers. */
  label?: string;
}

/**
 * Three choice cards: how much the bot may do without asking you. A level above the
 * organization's ceiling stays visible but unavailable, saying why; a bot already above it
 * (the ceiling was lowered later) keeps showing its own level, and can only move down.
 */
export function SecurityLevelPicker({ value, onChange, disabled, max, label = "Security level" }: SecurityLevelPickerProps) {
  const idPrefix = label === "Security level" ? "security" : label.toLowerCase().replace(/\W+/g, "-");
  return (
    <RadioGroup value={value} onValueChange={(v) => onChange(v as SecurityLevel)} disabled={disabled} aria-label={label} className="gap-2">
      {SECURITY_LEVELS.map((level) => {
        const Icon = ICON[level.value];
        const unavailable = max !== undefined && looserThan(level.value, max);
        const id = `${idPrefix}-${level.value}`;
        return (
          <FieldLabel key={level.value} htmlFor={id}>
            <Field orientation="horizontal" data-disabled={unavailable || undefined}>
              <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <FieldContent>
                <FieldTitle>
                  {level.label}
                  {level.value === "ask-before-acting" && <span className="rounded-full bg-brand/10 px-1.5 text-[11px] text-brand">Recommended</span>}
                </FieldTitle>
                <FieldDescription>{level.description}</FieldDescription>
                {unavailable && (
                  <FieldDescription id={`${id}-limit`} className="text-xs">
                    Above your organization&apos;s highest level ({securityLabel(max)}). Owners and admins can raise it in Settings → Security.
                  </FieldDescription>
                )}
              </FieldContent>
              <RadioGroupItem value={level.value} id={id} disabled={unavailable} aria-describedby={unavailable ? `${id}-limit` : undefined} />
            </Field>
          </FieldLabel>
        );
      })}
    </RadioGroup>
  );
}
