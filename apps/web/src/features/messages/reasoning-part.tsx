import { ChevronRight } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { ReasoningPart as ReasoningPartData } from "@/data/types";

/** "Thought for 6s": the bot's reasoning, closed by default so the chat stays calm. */
export function ReasoningPart({ part }: { part: ReasoningPartData }) {
  return (
    <Collapsible className="group/reasoning max-w-[560px]">
      <CollapsibleTrigger className="flex items-center gap-1 rounded-md text-xs text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
        <ChevronRight className="size-3.5 transition-transform group-data-[state=open]/reasoning:rotate-90" />
        Thought for {part.durationSec}s
      </CollapsibleTrigger>
      <CollapsibleContent>
        <p className="mt-1.5 border-l-2 pl-3 text-[13px] leading-relaxed text-muted-foreground">{part.text}</p>
      </CollapsibleContent>
    </Collapsible>
  );
}
