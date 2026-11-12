import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { actions, useAuthStatus } from "@/data/store";

/** Where to go after signing in: the page you were sent away from, or home. Only same-site paths. */
export function nextPath(): string {
  const next = new URLSearchParams(window.location.search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

/** On the auth pages: if you're already signed in on this device, skip straight into the app. */
export function useSignedInRedirect() {
  const status = useAuthStatus();
  const router = useRouter();

  useEffect(() => {
    if (status === "unknown") actions.restoreSession();
    if (status === "signed-in") router.replace(nextPath());
  }, [status, router]);
}
