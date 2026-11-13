import { Bubble, BubbleContent } from "@/components/ui/bubble";
import type { TextPart as TextPartData } from "@/data/types";
import { splitMentions } from "@/lib/mentions";
import { MarkdownText } from "./markdown";

/**
 * A chat bubble. Yours sit on the right in black; everyone else's on the left in grey.
 * Bots write markdown (lists, code, tables), so theirs is formatted; people's shows as typed.
 */
export function TextPart({ part, isOwn, isBot, isStreaming }: { part: TextPartData; isOwn: boolean; isBot: boolean; isStreaming?: boolean }) {
  // A streaming reply starts empty; the typing dots in the message show until words arrive.
  if (!part.text) return null;

  return (
    <Bubble variant={isOwn ? "default" : "muted"} align={isOwn ? "end" : "start"} className="max-w-[min(80%,560px)]">
      <BubbleContent className={isBot ? "rounded-2xl px-3.5 py-2.5 text-[14px]" : "rounded-2xl px-3.5 py-2 text-[14px] whitespace-pre-wrap"}>
        {isBot ? <MarkdownText text={part.text} /> : withMentions(part.text, isOwn)}
        {isStreaming && <span aria-hidden className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-current align-middle opacity-60" />}
      </BubbleContent>
    </Bubble>
  );
}

/** Shows @handles in the brand colour (bold on your own black bubble) so you can see who was pulled in. */
function withMentions(text: string, isOwn: boolean) {
  return splitMentions(text).map((piece, i) =>
    piece.isMention ? (
      <span key={i} className={isOwn ? "font-semibold" : "font-medium text-brand"}>
        {piece.text}
      </span>
    ) : (
      piece.text
    ),
  );
}
