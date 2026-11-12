import { Suspense } from "react";
import type { Metadata } from "next";
import { InviteScreen } from "@/features/auth/invite-screen";

export const metadata: Metadata = { title: "Join organization" };

/* Dynamic params resolve inside <Suspense>: the Next 16 + Cache Components pattern. */
export default function InvitePage({ params }: PageProps<"/invite/[token]">) {
  return <Suspense fallback={null}>{params.then(({ token }) => <InviteScreen token={token} />)}</Suspense>;
}
