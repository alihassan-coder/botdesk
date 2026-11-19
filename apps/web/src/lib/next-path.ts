/**
 * `path` if it's a page on this site, else `fallback`, so a link can't bounce you somewhere else.
 * Only "/…" counts: not a full URL, nor "//evil.com" or "/\evil.com" (browsers read both as
 * another site), nor a control character (browsers drop tabs and newlines, so "/\t/evil.com"
 * would become "//evil.com").
 */
export function sitePath(path: string | null | undefined, fallback: string): string {
  if (!path || !path.startsWith("/") || path.startsWith("//") || path.includes("\\")) return fallback;
  if ([...path].some((char) => char.charCodeAt(0) < 0x20 || char.charCodeAt(0) === 0x7f)) return fallback;
  return path;
}

/** Where to go after signing in: the `?next=` page you were sent away from, or home. */
export function safeNextPath(search: string): string {
  return sitePath(new URLSearchParams(search).get("next"), "/");
}

/**
 * The invite token when sign-up was opened from an invite link (`?next=/invite/<token>`), so the
 * new account can join that organization (and sign up at all when sign-up is invite-only).
 */
export function inviteTokenFromNext(next: string | undefined): string | null {
  return next?.match(/^\/invite\/([^/?#]+)$/)?.[1] ?? null;
}
