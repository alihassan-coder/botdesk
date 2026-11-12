"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { actions } from "@/data/store";
import { FormError } from "./form-error";
import { PasswordInput } from "./password-input";

const MIN_PASSWORD = 8;

/**
 * /reset-password?token=… — the page the reset email links to. Sets a new password; the link
 * works once, and every device is signed out, so you sign in again afterwards.
 */
export function ResetPasswordScreen({ token }: { token: string | null }) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, startSaving] = useTransition();
  const longEnough = password.length >= MIN_PASSWORD;

  if (!token) {
    return (
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">This link isn&apos;t complete</h1>
          <p className="mt-2 text-muted-foreground">Open the link from your reset email again, or ask for a new one.</p>
        </div>
        <NewLinkAndBack />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Choose a new password</h1>
        <p className="mt-2 text-muted-foreground">You&apos;ll be signed out everywhere, then sign in with the new one.</p>
      </div>
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (!longEnough) return;
          startSaving(async () => {
            const result = await actions.resetPassword(token, password);
            if (!result.ok) return setError(result.error);
            toast.success("Password changed. Sign in with your new password.");
            router.replace("/sign-in");
          });
        }}
      >
        <FieldGroup>
          {error && <FormError>{error}</FormError>}
          <Field>
            <FieldLabel htmlFor="password">New password</FieldLabel>
            <PasswordInput id="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            <FieldDescription className={password && !longEnough ? "text-destructive" : undefined}>
              At least {MIN_PASSWORD} characters{password ? ` · ${password.length}/${MIN_PASSWORD}` : ""}
            </FieldDescription>
          </Field>
          <Button type="submit" size="lg" disabled={!longEnough || saving}>
            {saving ? "Saving…" : "Set new password"}
          </Button>
        </FieldGroup>
      </form>
      <NewLinkAndBack />
    </div>
  );
}

function NewLinkAndBack() {
  return (
    <div className="flex items-center justify-between text-sm text-muted-foreground">
      <Link href="/sign-in" className="flex items-center gap-1.5 hover:text-foreground">
        <ArrowLeft className="size-4" /> Back to sign in
      </Link>
      <Link href="/forgot-password" className="hover:text-foreground">
        Get a new link
      </Link>
    </div>
  );
}
