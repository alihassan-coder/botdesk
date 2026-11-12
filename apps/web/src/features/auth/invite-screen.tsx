"use client";

import { useEffect, useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { actions, useAuthStatus, useCurrentUser, useOrg } from "@/data/store";
import { FormError } from "./form-error";

/**
 * /invite/[token] — the link from Settings → Members. Signed in, you accept it here;
 * signed out, you sign in (or create an account) with the invited email and come back.
 */
export function InviteScreen({ token }: { token: string }) {
  const status = useAuthStatus();

  useEffect(() => {
    if (status === "unknown") actions.restoreSession();
  }, [status]);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">You&apos;re invited</h1>
        <p className="mt-2 text-muted-foreground">Join your team&apos;s organization on botdesk and work with its bots.</p>
      </div>
      {status === "signed-in" && <AcceptInvite token={token} />}
      {status === "signed-out" && <SignInFirst token={token} />}
    </div>
  );
}

function AcceptInvite({ token }: { token: string }) {
  const me = useCurrentUser();
  const org = useOrg();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [joining, startJoining] = useTransition();
  const [joined, setJoined] = useState(false);

  // Once the store has switched to the new org, say so by name and go to the app.
  useEffect(() => {
    if (!joined) return;
    toast.success(`You joined ${org.name}`);
    router.replace("/");
  }, [joined, org.name, router]);

  const accept = () =>
    startJoining(async () => {
      const result = await actions.acceptInvitation(token);
      if (result.ok) setJoined(true);
      else setError(result.error);
    });

  return (
    <div className="flex flex-col gap-4">
      {error && <FormError>{error}</FormError>}
      <p className="text-sm text-muted-foreground">
        Signed in as <span className="font-medium text-foreground">{me.email}</span>
      </p>
      <Button size="lg" onClick={accept} disabled={joining || joined}>
        {joining ? "Joining…" : "Accept invite"}
      </Button>
      <Button variant="ghost" onClick={() => actions.signOut()}>
        Use a different account
      </Button>
    </div>
  );
}

function SignInFirst({ token }: { token: string }) {
  const next = `?next=${encodeURIComponent(`/invite/${token}`)}`;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">Sign in with the email the invite was sent to. New here? Create an account with that email.</p>
      <Button asChild size="lg">
        <Link href={`/sign-in${next}`}>Sign in</Link>
      </Button>
      <Button asChild size="lg" variant="outline">
        <Link href={`/sign-up${next}`}>Create an account</Link>
      </Button>
    </div>
  );
}
