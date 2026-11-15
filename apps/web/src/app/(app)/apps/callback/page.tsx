import { Suspense } from "react";
import type { Metadata } from "next";
import { OAuthCallbackScreen } from "@/features/apps/oauth-callback-screen";

export const metadata: Metadata = { title: "Connecting an app" };

const one = (value: string | string[] | undefined) => (typeof value === "string" && value ? value : null);

/* The API's OAuth callback sends the browser here (?result=connected|error&code=…). Search params resolve inside <Suspense>. */
export default function OAuthCallbackPage({ searchParams }: PageProps<"/apps/callback">) {
  return (
    <Suspense fallback={null}>
      {searchParams.then((params) => (
        <OAuthCallbackScreen result={one(params.result)} code={one(params.code)} connector={one(params.connector)} />
      ))}
    </Suspense>
  );
}
