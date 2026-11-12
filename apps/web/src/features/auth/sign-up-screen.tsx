"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { actions } from "@/data/store";
import { looksLikeEmail } from "@/lib/email";
import { FormError } from "./form-error";
import { PasswordInput } from "./password-input";
import { useSignedInRedirect } from "./use-signed-in-redirect";

const MIN_PASSWORD = 8;

/** /sign-up — name, email and a password of at least 8 characters. Signs you straight in. */
export function SignUpScreen() {
  useSignedInRedirect();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const emailValid = looksLikeEmail(email);
  const passwordLongEnough = password.length >= MIN_PASSWORD;
  const ready = name.trim() && emailValid && passwordLongEnough;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Create your account</h1>
        <p className="mt-2 text-muted-foreground">Then hire your first bot. It takes a minute.</p>
      </div>

      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (!ready) return;
          const result = actions.signUp({ name, email, password });
          setError(result.ok ? null : result.error);
        }}
      >
        <FieldGroup>
          {error && <FormError>{error}</FormError>}
          <Field>
            <FieldLabel htmlFor="name">Your name</FieldLabel>
            <Input id="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ali Hassan" />
          </Field>
          <Field data-invalid={email.length > 0 && !emailValid}>
            <FieldLabel htmlFor="email">Work email</FieldLabel>
            <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" aria-invalid={email.length > 0 && !emailValid} />
          </Field>
          <Field>
            <FieldLabel htmlFor="password">Password</FieldLabel>
            <PasswordInput id="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            <FieldDescription className={password && !passwordLongEnough ? "text-destructive" : undefined}>
              At least {MIN_PASSWORD} characters{password ? ` · ${password.length}/${MIN_PASSWORD}` : ""}
            </FieldDescription>
          </Field>
          <Button type="submit" size="lg" disabled={!ready}>
            Create account
          </Button>
          <p className="text-xs text-muted-foreground">By creating an account you agree to the terms and privacy policy.</p>
        </FieldGroup>
      </form>

      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/sign-in" className="font-medium text-foreground hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
