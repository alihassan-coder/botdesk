import { ShieldAlert, ShieldCheck, ShieldEllipsis } from "lucide-react";
import { Field, FieldContent, FieldDescription, FieldLabel, FieldTitle } from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { SecurityLevel } from "@/data/types";
import { SECURITY_LEVELS } from "./security-levels";

const ICON = { "read-only": ShieldCheck, "ask-before-acting": ShieldEllipsis, autonomous: ShieldAlert };

/** Three choice cards: how much the bot may do without asking you. */
export function SecurityLevelPicker({ value, onChange }: { value: SecurityLevel; onChange: (level: SecurityLevel) => void }) {
  return (
    <RadioGroup value={value} onValueChange={(v) => onChange(v as SecurityLevel)} aria-label="Security level" className="gap-2">
      {SECURITY_LEVELS.map((level) => {
        const Icon = ICON[level.value];
        return (
          <FieldLabel key={level.value} htmlFor={`security-${level.value}`}>
            <Field orientation="horizontal">
              <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <FieldContent>
                <FieldTitle>
                  {level.label}
                  {level.value === "ask-before-acting" && <span className="rounded-full bg-brand/10 px-1.5 text-[11px] text-brand">Recommended</span>}
                </FieldTitle>
                <FieldDescription>{level.description}</FieldDescription>
              </FieldContent>
              <RadioGroupItem value={level.value} id={`security-${level.value}`} />
            </Field>
          </FieldLabel>
        );
      })}
    </RadioGroup>
  );
}
