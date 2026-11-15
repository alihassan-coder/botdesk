"use client";

import Link from "next/link";
import { useSignUpMode } from "@/data/store";
import { ExploreDemoButton } from "./explore-demo-button";
import { SignUpForm } from "./sign-up-form";
import { useSignedInRedirect } from "./use-signed-in-redirect";

/**
 * /sign-up — what it offers depends on the server's sign-up mode: the form (open, or
 * invite-only when you came from an invite link), or a note saying how to get an account.
 */
export function SignUpScreen({ inviteToken }: { inviteToken: string | null }) {
  const mode = useSignUpMode();
  const canSignUp = mode === "open" || (mode === "invite-only" && inviteToken !== null);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Create your account</h1>
        <p className="mt-2 text-muted-foreground">
          {inviteToken ? "Then you join the organization that invited you." : "Then hire your first bot. It takes a minute."}
        </p>
      </div>

      {canSignUp && <SignUpForm inviteToken={inviteToken} />}
      {!canSignUp && <Redirect />}
      {mode === "invite-only" && !inviteToken && <Note>Sign-up is by invitation. Ask your admin for an invite link.</Note>}
      {mode === "closed" && <Note>New accounts are turned off on this server. Ask your admin if you need one.</Note>}

      <ExploreDemoButton />

      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/sign-in" className="tap-target font-medium text-foreground hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}

/** Without the form, someone already signed in (or entering the demo) still moves on. */
function Redirect() {
  useSignedInRedirect();
  return null;
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="rounded-xl border border-dashed px-3 py-2.5 text-sm text-muted-foreground">{children}</p>;
}
