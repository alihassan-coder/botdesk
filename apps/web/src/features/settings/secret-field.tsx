import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group";

interface SecretFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  problem?: string;
  /** A secret is already saved: an empty field keeps it. */
  keepsSaved: boolean;
}

/** A key or secret for Settings → Computers: hidden as you type (with Show), sent once, never shown again. */
export function SecretField({ id, label, value, onChange, problem, keepsSaved }: SecretFieldProps) {
  const [shown, setShown] = useState(false);
  return (
    <Field data-invalid={problem !== undefined}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <InputGroup>
        <InputGroupInput id={id} type={shown ? "text" : "password"} autoComplete="off" spellCheck={false} value={value}
          onChange={(e) => onChange(e.target.value)} placeholder={keepsSaved ? "Leave blank to keep the saved one" : undefined}
          aria-invalid={problem !== undefined} aria-describedby={problem ? `${id}-hint ${id}-error` : `${id}-hint`} />
        <InputGroupAddon align="inline-end">
          <InputGroupButton size="icon-xs" aria-pressed={shown} aria-label={`Show ${inSentence(label)}`} onClick={() => setShown((s) => !s)}>
            {shown ? <EyeOff /> : <Eye />}
          </InputGroupButton>
        </InputGroupAddon>
      </InputGroup>
      <FieldDescription id={`${id}-hint`}>Encrypted on the server and never shown again.</FieldDescription>
      {problem && <FieldError id={`${id}-error`}>{problem}</FieldError>}
    </Field>
  );
}

/** "Secret access key" → "secret access key", but "API key" stays "API key". */
function inSentence(label: string): string {
  return /^[A-Z][a-z]/.test(label) ? label[0].toLowerCase() + label.slice(1) : label;
}
