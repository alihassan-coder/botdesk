import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { actions, useAuthStatus } from "@/data/store";
import { safeNextPath } from "@/lib/next-path";

/** On the auth pages: if you're already signed in on this device, skip straight into the app. */
export function useSignedInRedirect() {
  const status = useAuthStatus();
  const router = useRouter();

  useEffect(() => {
    if (status === "unknown") actions.restoreSession();
    if (status === "signed-in") router.replace(safeNextPath(window.location.search));
  }, [status, router]);
}
