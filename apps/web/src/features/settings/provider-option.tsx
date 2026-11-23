import { RadioGroupItem } from "@/components/ui/radio-group";

interface ProviderOptionProps {
  /** Makes the ids unique: "storage", "browser". */
  group: string;
  value: string;
  label: string;
  hint: string;
  disabled?: boolean;
  autoFocus?: boolean;
}

/** One provider to pick in Settings → Computers (Local, S3-compatible, Steel…), with a line on what it is. */
export function ProviderOption({ group, value, label, hint, disabled, autoFocus }: ProviderOptionProps) {
  const id = `${group}-${value}`;
  return (
    <div className="flex items-start gap-2.5">
      <RadioGroupItem id={id} value={value} disabled={disabled} autoFocus={autoFocus} className="mt-0.5" />
      <label htmlFor={id} className="text-sm peer-disabled:opacity-50">
        <span className="font-medium">{label}</span>
        <span className="block text-xs text-muted-foreground">{hint}</span>
      </label>
    </div>
  );
}
