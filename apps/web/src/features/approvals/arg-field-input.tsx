import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { ArgField } from "@/lib/args-form";

/** Radix Select can't hold an empty value, so an optional choice's "None" has a name of its own. */
const NONE = "__none__";

interface ArgFieldInputProps {
  field: ArgField;
  value: string | boolean;
  error?: string;
  idPrefix: string;
  onChange: (value: string | boolean) => void;
}

/** One argument of an action in the Edit form: the right input for its type, and what's wrong with it. */
export function ArgFieldInput({ field, value, error, idPrefix, onChange }: ArgFieldInputProps) {
  const id = `${idPrefix}-${field.name}`;
  const invalid = error ? true : undefined;
  const describedBy = error ? `${id}-error` : undefined;

  if (field.kind === "boolean") {
    return (
      <Field orientation="horizontal" data-invalid={invalid}>
        <Checkbox id={id} checked={value === true} onCheckedChange={(checked) => onChange(checked === true)} aria-invalid={invalid} />
        <FieldLabel htmlFor={id} className="font-normal">{field.label}</FieldLabel>
        {error && <FieldError id={describedBy}>{error}</FieldError>}
      </Field>
    );
  }

  const text = typeof value === "string" ? value : "";
  const common = {
    id, value: text, required: field.required, "aria-invalid": invalid, "aria-describedby": describedBy,
  };

  return (
    <Field data-invalid={invalid} className="gap-1.5">
      <FieldLabel htmlFor={id} className="text-xs text-muted-foreground">
        {field.label}
        {!field.required && <span className="font-normal"> (optional)</span>}
      </FieldLabel>
      {field.kind === "enum" ? (
        // A required choice with nothing picked yet shows "Pick one" (an empty value is the placeholder).
        <Select value={text === "" && !field.required ? NONE : text} required={field.required} onValueChange={(v) => onChange(v === NONE ? "" : v)}>
          <SelectTrigger id={id} aria-invalid={invalid} aria-describedby={describedBy} className="w-full">
            <SelectValue placeholder="Pick one" />
          </SelectTrigger>
          <SelectContent>
            {!field.required && <SelectItem value={NONE}>None</SelectItem>}
            {field.options?.map((option) => (
              <SelectItem key={option} value={option}>{option}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : field.kind === "textarea" ? (
        <Textarea {...common} rows={5} maxLength={field.maxLength} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <Input
          {...common}
          type={field.kind === "number" ? "number" : field.email ? "email" : "text"}
          step={field.kind === "number" && !field.integer ? "any" : undefined}
          maxLength={field.maxLength}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {field.description && !error && <FieldDescription className="text-xs">{field.description}</FieldDescription>}
      {error && <FieldError id={describedBy} className="text-xs">{error}</FieldError>}
    </Field>
  );
}
