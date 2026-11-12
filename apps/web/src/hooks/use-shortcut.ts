import { useSyncExternalStore } from "react";
import { formatShortcut, isApplePlatform } from "@/lib/platform";

type NavigatorWithUAData = Navigator & { userAgentData?: { platform?: string } };

// The platform never changes while the page is open, so there is nothing to subscribe to.
const subscribe = () => () => {};

function detectApple() {
  const nav = navigator as NavigatorWithUAData;
  return isApplePlatform(nav.userAgentData?.platform || nav.platform);
}

/**
 * Formats a Cmd/Ctrl shortcut for this device: "⌘K" on macOS/iOS, "Ctrl+K" elsewhere.
 * The server can't know the device, so it renders the Ctrl form and the browser corrects it after hydration.
 */
export function useShortcut(key: string): string {
  const apple = useSyncExternalStore(subscribe, detectApple, () => false);
  return formatShortcut(key, apple);
}
