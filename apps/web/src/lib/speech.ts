/**
 * Reading a bot's reply aloud (ADR 0021 §3): markdown made into words worth hearing, in chunks the
 * browser's speech synthesis reads whole (Chrome stops a long utterance after about 15 seconds).
 */

const MAX_CHUNK = 220;

/** What a markdown reply sounds like: code blocks become "Code block.", links their words, bare addresses "a link". */
export function speakableText(markdown: string): string {
  return (
    markdown
      .replace(/```[\s\S]*?(```|$)/g, "\nCode block.\n")
      .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/https?:\/\/\S+/g, "a link")
      .replace(/^\s{0,3}#{1,6}\s+/gm, "")
      .replace(/^\s*>\s?/gm, "")
      .replace(/^\s*(?:[-*+]|\d+[.)])\s+/gm, "")
      .replace(/^[ \t]*\|?(?:[ \t]*:?-{3,}:?[ \t]*\|)+[ \t]*:?-*:?[ \t]*$/gm, "")
      .replace(/[ \t]*\|[ \t]*/g, ", ")
      .replace(/(\*\*|__|\*|_|~~)(\S(?:.*?\S)?)\1/g, "$2")
      // A line that doesn't end a sentence still deserves a pause when read.
      .split("\n")
      .map((line) => line.replace(/\s+/g, " ").trim().replace(/^,\s*|,\s*$/g, "").trim())
      .filter(Boolean)
      .map((line) => (/[.!?:;]$/.test(line) ? line : `${line}.`))
      .join(" ")
  );
}

/** Sentences grouped into pieces of at most `max` characters; a longer sentence is cut at a space. */
export function speechChunks(text: string, max = MAX_CHUNK): string[] {
  const sentences = text.match(/[^.!?]+[.!?]+["')\]]*|[^.!?]+$/g)?.map((s) => s.trim()).filter(Boolean) ?? [];
  const chunks: string[] = [];
  let current = "";
  const push = () => {
    if (current) chunks.push(current);
    current = "";
  };
  for (const sentence of sentences) {
    if (sentence.length > max) {
      push();
      let rest = sentence;
      while (rest.length > max) {
        const cut = rest.lastIndexOf(" ", max);
        const at = cut > max / 2 ? cut : max;
        chunks.push(rest.slice(0, at).trim());
        rest = rest.slice(at).trim();
      }
      current = rest;
    } else if (current && current.length + 1 + sentence.length > max) {
      push();
      current = sentence;
    } else {
      current = current ? `${current} ${sentence}` : sentence;
    }
  }
  push();
  return chunks;
}

/** The voice that reads best: one for the page's language, preferring natural-sounding ones. */
export function bestVoice(voices: SpeechSynthesisVoice[], lang: string): SpeechSynthesisVoice | undefined {
  const base = lang.toLowerCase().split("-")[0];
  const matching = voices.filter((v) => v.lang.toLowerCase().startsWith(base));
  const pool = matching.length ? matching : voices;
  const score = (v: SpeechSynthesisVoice) =>
    (/natural|neural|online/i.test(v.name) ? 4 : 0) +
    (/google/i.test(v.name) ? 2 : 0) +
    (v.lang.toLowerCase() === lang.toLowerCase() ? 1 : 0) +
    (v.default ? 0.5 : 0);
  return [...pool].sort((a, b) => score(b) - score(a))[0];
}
