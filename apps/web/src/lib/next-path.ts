/**
 * Where to go after signing in: the `?next=` page you were sent away from, or home.
 * Only paths on this site count; "//evil.com" and "/\evil.com" (browsers read both as
 * another site) fall back to home, so a link can't bounce you somewhere else.
 */
export function safeNextPath(search: string): string {
  const next = new URLSearchParams(search).get("next");
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return "/";
  return next;
}

/**
 * The invite token when sign-up was opened from an invite link (`?next=/invite/<token>`), so the
 * new account can join that organization (and sign up at all when sign-up is invite-only).
 */
export function inviteTokenFromNext(next: string | undefined): string | null {
  return next?.match(/^\/invite\/([^/?#]+)$/)?.[1] ?? null;
}
