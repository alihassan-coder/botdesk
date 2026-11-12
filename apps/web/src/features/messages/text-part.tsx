import { Bubble, BubbleContent } from "@/components/ui/bubble";
import type { TextPart as TextPartData } from "@/data/types";

// SPLIT keeps the @handles as their own pieces; IS_MENTION checks a piece (no "g" flag, so no hidden state).
const SPLIT = /(@[a-z0-9_-]+)/gi;
const IS_MENTION = /^@[a-z0-9_-]+$/i;

/** A chat bubble. Yours sit on the right in black; everyone else's on the left in grey. */
export function TextPart({ part, isOwn, isStreaming }: { part: TextPartData; isOwn: boolean; isStreaming?: boolean }) {
  // A streaming reply starts empty; the typing dots in the message show until words arrive.
  if (!part.text) return null;

  return (
    <Bubble variant={isOwn ? "default" : "muted"} align={isOwn ? "end" : "start"} className="max-w-[min(80%,560px)]">
      <BubbleContent className="rounded-2xl px-3.5 py-2 text-[14px] whitespace-pre-wrap">
        {withMentions(part.text, isOwn)}
        {isStreaming && <span aria-hidden className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-current align-middle opacity-60" />}
      </BubbleContent>
    </Bubble>
  );
}

/** Shows @handles in the brand colour so you can see who was pulled in. */
function withMentions(text: string, isOwn: boolean) {
  return text.split(SPLIT).map((piece, i) =>
    IS_MENTION.test(piece) ? (
      <span key={i} className={isOwn ? "font-semibold" : "font-medium text-brand"}>
        {piece}
      </span>
    ) : (
      piece
    ),
  );
}
