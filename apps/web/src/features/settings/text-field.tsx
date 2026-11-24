import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

interface TextFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  problem?: string;
  hint?: string;
  placeholder?: string;
  inputMode?: "url";
}

/** A plain text field for Settings → Computers forms: a label, an optional hint, and its problem once a save was tried. */
export function TextField({ id, label, value, onChange, problem, hint, placeholder, inputMode }: TextFieldProps) {
  return (
    <Field data-invalid={problem !== undefined}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} inputMode={inputMode}
        autoComplete="off" autoCapitalize="none" spellCheck={false} aria-invalid={problem !== undefined}
        aria-describedby={[hint && `${id}-hint`, problem && `${id}-error`].filter(Boolean).join(" ") || undefined} />
      {hint && <FieldDescription id={`${id}-hint`}>{hint}</FieldDescription>}
      {problem && <FieldError id={`${id}-error`}>{problem}</FieldError>}
    </Field>
  );
}
