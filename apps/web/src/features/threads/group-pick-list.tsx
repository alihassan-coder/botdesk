import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field";

export interface PickOption {
  id: string;
  name: string;
  detail: string;
  avatar: React.ReactNode;
}

/** A titled list of checkboxes with avatars, for picking who joins a group. */
export function GroupPickList({
  legend,
  options,
  picked,
  onToggle,
}: {
  legend: string;
  options: PickOption[];
  picked: string[];
  onToggle: (id: string) => void;
}) {
  return (
    <FieldSet className="gap-2">
      <FieldLegend variant="label" className="mb-0">{legend}</FieldLegend>
      <div className="flex flex-col gap-0.5">
        {options.map((o) => {
          const fieldId = `group-pick-${o.id}`;
          return (
            <Field key={o.id} orientation="horizontal" className="rounded-lg px-2 py-1.5 hover:bg-muted/50 has-data-checked:bg-muted/70">
              <Checkbox id={fieldId} checked={picked.includes(o.id)} onCheckedChange={() => onToggle(o.id)} />
              <FieldLabel htmlFor={fieldId} className="min-w-0 items-center gap-3 font-normal">
                {o.avatar}
                <span className="flex min-w-0 flex-col">
                  <span className="truncate text-sm font-medium">{o.name}</span>
                  <span className="truncate text-xs text-muted-foreground">{o.detail}</span>
                </span>
              </FieldLabel>
            </Field>
          );
        })}
      </div>
    </FieldSet>
  );
}
