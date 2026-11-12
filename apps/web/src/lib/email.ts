/** A light check that this could be an email address (something@domain.tld). The server decides the rest. */
export function looksLikeEmail(text: string): boolean {
  return /^\S+@\S+\.\S+$/.test(text.trim());
}
