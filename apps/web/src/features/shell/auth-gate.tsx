import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { actions, useAuthStatus } from "@/data/store";
import { BotdeskMark } from "./logo";
import { useApprovalsPolling } from "./use-approvals-polling";

/**
 * Shows the app only to signed-in people. On first load it checks for a saved session;
 * if there isn't one, it sends you to sign in and brings you back here afterwards.
 * Signing out (from the user menu) goes to a plain sign-in page, since you chose to leave.
 *
 * The page is always rendered, just hidden and inert until you're signed in. Next.js
 * prerenders every route segment under this gate (Cache Components checks that each
 * one renders, for instant navigation), and the session is only known in the browser,
 * so leaving `children` out would drop every page from the prerender.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const status = useAuthStatus();
  const router = useRouter();
  const wasSignedIn = useRef(false);
  const signedIn = status === "signed-in";
  useApprovalsPolling();

  useEffect(() => {
    if (status === "unknown") actions.restoreSession();
    if (status === "signed-in") wasSignedIn.current = true;
    if (status === "signed-out") router.replace(wasSignedIn.current ? "/sign-in" : signInAndComeBack());
  }, [status, router]);

  return (
    <>
      {!signedIn && (
        <div className="grid h-svh place-items-center" aria-busy="true" aria-label="Loading botdesk">
          <BotdeskMark className="size-9 animate-pulse text-muted-foreground/50" />
        </div>
      )}
      <div hidden={!signedIn} inert={!signedIn} className="contents">
        {children}
      </div>
    </>
  );
}

function signInAndComeBack() {
  const here = window.location.pathname + window.location.search;
  return here === "/" ? "/sign-in" : `/sign-in?next=${encodeURIComponent(here)}`;
}
