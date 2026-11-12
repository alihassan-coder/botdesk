/** Lowercase a–z, 0–9 and single dashes. Accents are dropped ("é" → "e"), anything else becomes a dash. */
function toDashed(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-");
}

/**
 * Turns a bot's name into its @handle: lowercase, words joined by "-", only a–z, 0–9, "-".
 * If the handle is taken, adds -2, -3… until it's free.
 */
export function makeHandle(name: string, taken: string[]): string {
  const base = toDashed(name).replace(/^-+|-+$/g, "").slice(0, 24) || "bot";

  if (!taken.includes(base)) return base;
  let n = 2;
  while (taken.includes(`${base}-${n}`)) n++;
  return `${base}-${n}`;
}

/**
 * An organization's web address while it's being typed. Same rules as a handle, but a
 * trailing dash stays (you may be about to type the next word) and empty stays empty.
 * Trim the trailing dash with `finishSlug` when saving.
 */
export function slugWhileTyping(text: string): string {
  return toDashed(text).replace(/^-+/, "").slice(0, 40);
}

/** The address to save: no dash at the end. */
export function finishSlug(slug: string): string {
  return slug.replace(/-+$/, "");
}
