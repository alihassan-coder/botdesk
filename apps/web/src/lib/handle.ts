/**
 * Turns a bot's name into its @handle: lowercase, words joined by "-", only a–z, 0–9, "-".
 * If the handle is taken, adds -2, -3… until it's free.
 */
export function makeHandle(name: string, taken: string[]): string {
  const base =
    name
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 24) || "bot";

  if (!taken.includes(base)) return base;
  let n = 2;
  while (taken.includes(`${base}-${n}`)) n++;
  return `${base}-${n}`;
}
