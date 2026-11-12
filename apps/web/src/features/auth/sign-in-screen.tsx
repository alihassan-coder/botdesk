"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { CircleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { actions } from "@/data/store";
import { PasswordInput } from "./password-input";
import { useSignedInRedirect } from "./use-signed-in-redirect";

/** /sign-in — email and password. On success you land where you were going. */
export function SignInScreen() {
  useSignedInRedirect();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Welcome back</h1>
        <p className="mt-2 text-muted-foreground">Sign in to your team&apos;s bots.</p>
      </div>

      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          const result = actions.signIn(email, password);
          setError(result.ok ? null : result.error);
        }}
      >
        <FieldGroup>
          {error && (
            <p role="alert" className="flex items-center gap-2 rounded-xl bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
              <CircleAlert className="size-4 shrink-0" /> {error}
            </p>
          )}
          <Field>
            <FieldLabel htmlFor="email">Email</FieldLabel>
            <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" required />
          </Field>
          <Field>
            <div className="flex items-center">
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <Link href="/forgot-password" className="ml-auto text-sm text-muted-foreground hover:text-foreground">
                Forgot password?
              </Link>
            </div>
            <PasswordInput id="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          <Button type="submit" size="lg" disabled={!email || !password}>
            Sign in
          </Button>
        </FieldGroup>
      </form>

      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
      </div>
      <Button variant="outline" size="lg" onClick={() => toast("Google sign-in arrives with accounts on the API.")}>
        Continue with Google
      </Button>

      <p className="text-center text-sm text-muted-foreground">
        New to botdesk?{" "}
        <Link href="/sign-up" className="font-medium text-foreground hover:underline">
          Create an account
        </Link>
      </p>

      {/* MOCK: until accounts live on the API, these demo logins exist. */}
      <p className="rounded-xl border border-dashed px-3 py-2.5 text-xs text-muted-foreground">
        Demo account: <span className="font-medium text-foreground">ali@acme.dev</span> · password <span className="font-medium text-foreground">botdesk123</span>
      </p>
    </div>
  );
}
