import { useEffect } from "react";
import { actions, useAuthStatus, useIsGuest, useOrg } from "@/data/store";

/** How often the chat list (unread counts, previews) is checked while the tab is in view. */
export const CHAT_LIST_POLL_MS = 20_000;

/**
 * Keeps the chat list's unread counts current. Only open chats have a live stream, so the list
 * is fetched again every 20 seconds while this tab is visible, and when you come back to it. It
 * also brings in groups you were added to and drops ones you were removed from.
 * The org's first load fetches the list already, so this doesn't on mount.
 */
export function useChatListPolling() {
  const signedIn = useAuthStatus() === "signed-in";
  const isGuest = useIsGuest();
  const orgId = useOrg().id;

  useEffect(() => {
    if (!signedIn || isGuest) return;
    const refresh = () => {
      if (document.visibilityState === "visible") void actions.refreshChats();
    };
    const timer = setInterval(refresh, CHAT_LIST_POLL_MS);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [signedIn, isGuest, orgId]);
}
