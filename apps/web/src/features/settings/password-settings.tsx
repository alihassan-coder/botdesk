import { useState, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { actions, isDemoMode } from "@/data/store";
import { FormError } from "@/features/auth/form-error";
import { PasswordInput } from "@/features/auth/password-input";
import { SettingsSection } from "./settings-shell";

const MIN_LENGTH = 8;

/** Settings → Profile → Password. Needs your current one; other devices are signed out. */
export function PasswordSettings() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, startSaving] = useTransition();
  const ready = current.length > 0 && next.length >= MIN_LENGTH;

  const save = () =>
    startSaving(async () => {
      setError(null);
      const result = await actions.changePassword(current, next);
      if (!result.ok) return setError(result.error);
      setCurrent("");
      setNext("");
      toast.success(isDemoMode() ? "Password changed" : "Password changed. Your other devices are signed out.");
    });

  return (
    <SettingsSection title="Password" description="You stay signed in here; anywhere else you're signed in has to sign in again.">
      <form
        className="max-w-md"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <FieldGroup>
          {error && <FormError>{error}</FormError>}
          <Field>
            <FieldLabel htmlFor="current-password">Current password</FieldLabel>
            <PasswordInput id="current-password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
          </Field>
          <Field>
            <FieldLabel htmlFor="new-password">New password</FieldLabel>
            <PasswordInput id="new-password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
            <FieldDescription>At least {MIN_LENGTH} characters.</FieldDescription>
          </Field>
          <Button type="submit" disabled={!ready || saving} className="w-fit">
            {saving ? "Changing…" : "Change password"}
          </Button>
        </FieldGroup>
      </form>
    </SettingsSection>
  );
}
