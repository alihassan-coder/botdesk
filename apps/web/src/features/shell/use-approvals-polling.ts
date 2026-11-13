import { useEffect } from "react";
import { actions, useAuthStatus, useIsGuest, useOrg } from "@/data/store";

/** How often the waiting-approvals count is checked while the tab is in view. */
export const APPROVALS_POLL_MS = 20_000;

/**
 * Keeps the "Approvals" count in the sidebar current. There's no org-wide event stream yet,
 * so the list of waiting approvals is fetched every 20 seconds, only while this tab is
 * visible (a background tab doesn't need it), and at once when you come back to it.
 * Open chats update the count straight away from their own events.
 */
export function useApprovalsPolling() {
  const signedIn = useAuthStatus() === "signed-in";
  const isGuest = useIsGuest();
  const orgId = useOrg().id;

  useEffect(() => {
    if (!signedIn || isGuest) return;
    const refresh = () => {
      if (document.visibilityState === "visible") void actions.refreshPendingApprovals();
    };
    refresh();
    const timer = setInterval(refresh, APPROVALS_POLL_MS);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [signedIn, isGuest, orgId]);
}
