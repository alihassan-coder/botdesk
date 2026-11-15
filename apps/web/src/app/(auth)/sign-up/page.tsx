import { Suspense } from "react";
import type { Metadata } from "next";
import { SignUpScreen } from "@/features/auth/sign-up-screen";
import { inviteTokenFromNext } from "@/lib/next-path";

export const metadata: Metadata = { title: "Create your account" };

/* From an invite link the page is /sign-up?next=/invite/<token>. Search params resolve inside <Suspense>. */
export default function Page({ searchParams }: PageProps<"/sign-up">) {
  return (
    <Suspense fallback={null}>
      {searchParams.then(({ next }) => (
        <SignUpScreen inviteToken={inviteTokenFromNext(typeof next === "string" ? next : undefined)} />
      ))}
    </Suspense>
  );
}
