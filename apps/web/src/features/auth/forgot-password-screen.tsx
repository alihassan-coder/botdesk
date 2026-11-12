"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, MailCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

/**
 * /forgot-password — ask for a reset link. The answer is the same whether or not the
 * email has an account, so this page can't be used to find out who's signed up.
 */
export function ForgotPasswordScreen() {
  const [email, setEmail] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const valid = /^\S+@\S+\.\S+$/.test(email);

  if (sentTo) {
    return (
      <div className="flex flex-col gap-6">
        <MailCheck className="size-10 text-brand" />
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Check your email</h1>
          <p className="mt-2 text-muted-foreground">
            If <span className="font-medium text-foreground">{sentTo}</span> has an account, a link to reset your password is on its way. It works for 30 minutes.
          </p>
        </div>
        <BackToSignIn />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Reset your password</h1>
        <p className="mt-2 text-muted-foreground">Enter your email and we&apos;ll send you a reset link.</p>
      </div>
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          // MOCK: the API sends the email (Better Auth). Here we only confirm.
          if (valid) setSentTo(email.trim());
        }}
      >
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="email">Email</FieldLabel>
            <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
          </Field>
          <Button type="submit" size="lg" disabled={!valid}>
            Send reset link
          </Button>
        </FieldGroup>
      </form>
      <BackToSignIn />
    </div>
  );
}

function BackToSignIn() {
  return (
    <Link href="/sign-in" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" /> Back to sign in
    </Link>
  );
}
