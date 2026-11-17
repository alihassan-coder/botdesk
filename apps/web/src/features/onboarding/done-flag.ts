/* Finishing or skipping setup, remembered per organization in this browser (a preference, like the sidebar). */
const key = (orgId: string) => `botdesk.onboarding.done.${orgId}`;

export function onboardingDone(orgId: string) {
  try {
    return localStorage.getItem(key(orgId)) === "1";
  } catch {
    return false;
  }
}

export function markOnboardingDone(orgId: string) {
  try {
    localStorage.setItem(key(orgId), "1");
  } catch {}
}
