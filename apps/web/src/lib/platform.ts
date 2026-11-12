/** True on macOS and iOS/iPadOS, where shortcuts use ⌘ instead of Ctrl. */
export function isApplePlatform(platform: string | undefined | null): boolean {
  return /mac|iphone|ipad|ipod|ios/i.test(platform ?? "");
}

/** How a Cmd/Ctrl shortcut is written: "⌘K" on Apple devices, "Ctrl+K" everywhere else. */
export function formatShortcut(key: string, apple: boolean): string {
  return apple ? `⌘${key.toUpperCase()}` : `Ctrl+${key.toUpperCase()}`;
}
