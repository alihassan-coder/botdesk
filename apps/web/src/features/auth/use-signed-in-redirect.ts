import { useEffect, type RefObject } from "react";
import { useRouter } from "next/navigation";
import { actions, useAuthStatus } from "@/data/store";
import { safeNextPath } from "@/lib/next-path";

/**
 * On the auth pages: if you're already signed in on this device, skip straight into the app.
 * `landing`, when set, wins over `?next=`: signing up with an invite has already joined its
 * organization, so going back to the invite page would only show a used link.
 */
export function useSignedInRedirect(landing?: RefObject<string | null>) {
  const status = useAuthStatus();
  const router = useRouter();

  useEffect(() => {
    if (status === "unknown") actions.restoreSession();
    if (status === "signed-in") router.replace(landing?.current ?? safeNextPath(window.location.search));
  }, [status, router, landing]);
}
