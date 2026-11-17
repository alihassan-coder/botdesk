import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { actions, useOrg } from "@/data/store";
import { StepFrame } from "./step-frame";

/** Step 1: the organization's name, prefilled with the one sign-up made. Saved only if changed. */
export function OrgStep({ onNext }: { onNext: () => void }) {
  const org = useOrg();
  const [name, setName] = useState(org.name);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const trimmed = name.trim();

  async function save() {
    if (trimmed === org.name) return onNext();
    setSaving(true);
    setError("");
    const result = await actions.updateOrg({ name: trimmed });
    setSaving(false);
    if (!result.ok) return setError(result.error);
    onNext();
  }

  return (
    <form noValidate onSubmit={(e) => { e.preventDefault(); if (trimmed && !saving) void save(); }}>
      <StepFrame
        title="Name your organization"
        description="It's what your team sees in the sidebar and in invites. You can change it later in Settings."
        onSkip={onNext}
        action={<Button type="submit" disabled={!trimmed || saving}>{saving ? "Saving…" : "Continue"}</Button>}
      >
        <Field data-invalid={error !== ""}>
          <FieldLabel htmlFor="setup-org-name">Organization name</FieldLabel>
          <Input id="setup-org-name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="organization" aria-invalid={error !== ""} autoFocus />
          {error ? <FieldError>{error}</FieldError> : <FieldDescription>Your company or team, like &ldquo;Acme&rdquo;.</FieldDescription>}
        </Field>
      </StepFrame>
    </form>
  );
}
