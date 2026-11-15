/**
 * Full-page moves to another site (an OAuth provider's sign-in). An object, so tests can
 * `vi.spyOn(browser, "leaveFor")` instead of navigating jsdom.
 */
export const browser = {
  leaveFor(url: string): void {
    window.location.assign(url);
  },
};
