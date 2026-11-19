/**
 * Full-page moves to another site (an OAuth provider's sign-in). An object, so tests can
 * `vi.spyOn(browser, "leaveFor")` instead of navigating jsdom.
 */
export const browser = {
  leaveFor(url: string): void {
    window.location.assign(url);
  },
  /** The page this tab is on (path and query), to come back to after leaving. */
  here(): string {
    return `${window.location.pathname}${window.location.search}`;
  },
};
