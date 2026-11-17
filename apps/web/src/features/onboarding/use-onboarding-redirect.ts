import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStatus, useBots, useBotsLoading, useCurrentUser, useIsDemo, useOrg } from "@/data/store";
import { needsOnboarding } from "@/lib/onboarding";
import { onboardingDone } from "./done-flag";

/** On "/": the owner of a brand-new organization goes to first-time setup instead. */
export function useOnboardingRedirect() {
  const router = useRouter();
  const signedIn = useAuthStatus() === "signed-in";
  const demo = useIsDemo();
  const botsLoading = useBotsLoading();
  const botCount = useBots().length;
  const role = useCurrentUser()?.role ?? "member";
  const orgId = useOrg().id;

  useEffect(() => {
    if (!signedIn || !orgId) return;
    // The flag is read here, not during render: localStorage only exists in the browser.
    if (needsOnboarding({ demo, botsLoading, botCount, role, done: onboardingDone(orgId) })) router.replace("/welcome");
  }, [signedIn, demo, botsLoading, botCount, role, orgId, router]);
}
