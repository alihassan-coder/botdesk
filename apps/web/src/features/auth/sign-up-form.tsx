import { useRef, useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { actions } from "@/data/store";
import { looksLikeEmail } from "@/lib/email";
import { FormError } from "./form-error";
import { PasswordInput } from "./password-input";
import { useSignedInRedirect } from "./use-signed-in-redirect";

const MIN_PASSWORD = 8;

/**
 * Name, email and a password of at least 8 characters. Signs you straight in. With an invite
 * token, the account joins that organization, and you land in it rather than on the used link.
 */
export function SignUpForm({ inviteToken }: { inviteToken: string | null }) {
  const landing = useRef<string | null>(null);
  useSignedInRedirect(landing);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, startCreating] = useTransition();

  const emailValid = looksLikeEmail(email);
  const passwordLongEnough = password.length >= MIN_PASSWORD;
  const ready = name.trim() && emailValid && passwordLongEnough;

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        if (!ready) return;
        // Set before the call: the redirect runs as soon as the session starts.
        landing.current = inviteToken ? "/" : null;
        startCreating(async () => {
          const result = await actions.signUp({ name, email, password, ...(inviteToken ? { inviteToken } : {}) });
          if (!result.ok) landing.current = null;
          setError(result.ok ? null : result.error);
        });
      }}
    >
      <FieldGroup>
        {error && <FormError>{error}</FormError>}
        <Field>
          <FieldLabel htmlFor="sign-up-name">Your name</FieldLabel>
          <Input id="sign-up-name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ali Hassan" />
        </Field>
        <Field data-invalid={email.length > 0 && !emailValid}>
          <FieldLabel htmlFor="sign-up-email">Work email</FieldLabel>
          <Input id="sign-up-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" aria-invalid={email.length > 0 && !emailValid} />
          {inviteToken && <FieldDescription>Use the email your invite was sent to.</FieldDescription>}
        </Field>
        <Field>
          <FieldLabel htmlFor="sign-up-password">Password</FieldLabel>
          <PasswordInput id="sign-up-password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <FieldDescription className={password && !passwordLongEnough ? "text-destructive" : undefined}>
            At least {MIN_PASSWORD} characters{password ? ` · ${password.length}/${MIN_PASSWORD}` : ""}
          </FieldDescription>
        </Field>
        <Button type="submit" size="lg" disabled={!ready || creating}>
          {creating ? "Creating account…" : "Create account"}
        </Button>
        <p className="text-xs text-muted-foreground">By creating an account you agree to the terms and privacy policy.</p>
      </FieldGroup>
    </form>
  );
}
