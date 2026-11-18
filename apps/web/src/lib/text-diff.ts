/** One piece of a diff: kept as it was, taken out, or put in. */
export interface DiffPart {
  kind: "same" | "removed" | "added";
  text: string;
}

/** Past this many comparisons the diff gives up on lining things up and shows all before, then all after. */
const MAX_CELLS = 250_000;

/**
 * The shortest edit from `before` to `after` (longest common subsequence), with neighbouring
 * pieces of the same kind joined. Pure and small: tool descriptions and schemas, not files.
 */
export function diffTokens(before: string[], after: string[], join = ""): DiffPart[] {
  const n = before.length;
  const m = after.length;
  if (n * m > MAX_CELLS) return merge([...before.map((text) => part("removed", text)), ...after.map((text) => part("added", text))], join);
  // lengths[i][j]: the longest common run of before[i..] and after[j..].
  const lengths = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lengths[i][j] = before[i] === after[j] ? lengths[i + 1][j + 1] + 1 : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }
  const parts: DiffPart[] = [];
  let i = 0;
  let j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && before[i] === after[j]) {
      parts.push(part("same", before[i]));
      i++;
      j++;
    } else if (i < n && (j === m || lengths[i + 1][j] >= lengths[i][j + 1])) {
      parts.push(part("removed", before[i])); // what went comes before what replaced it
      i++;
    } else {
      parts.push(part("added", after[j]));
      j++;
    }
  }
  return merge(parts, join);
}

/** Word by word, keeping the spaces, for prose (a tool's description). */
export function wordDiff(before: string, after: string): DiffPart[] {
  const words = (text: string) => text.split(/(\s+)/).filter((token) => token !== "");
  return diffTokens(words(before), words(after));
}

/** Line by line, for structured text (a schema as JSON). Each part's text is its lines joined by "\n". */
export function lineDiff(before: string, after: string): DiffPart[] {
  const lines = (text: string) => (text === "" ? [] : text.split("\n"));
  return diffTokens(lines(before), lines(after), "\n");
}

/** JSON with its keys sorted, two spaces in: the same schema always reads the same, so only real changes show. */
export function stableJson(value: unknown): string {
  return JSON.stringify(sortKeys(value), null, 2) ?? "null";
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)).map(([k, v]) => [k, sortKeys(v)]));
  }
  return value;
}

function part(kind: DiffPart["kind"], text: string): DiffPart {
  return { kind, text };
}

function merge(parts: DiffPart[], join: string): DiffPart[] {
  const merged: DiffPart[] = [];
  for (const piece of parts) {
    const last = merged[merged.length - 1];
    if (last && last.kind === piece.kind) last.text += join + piece.text;
    else merged.push({ ...piece });
  }
  return merged;
}
