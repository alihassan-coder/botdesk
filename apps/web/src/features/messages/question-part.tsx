import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { actions } from "@/data/store";
import type { QuestionPart as QuestionPartData } from "@/data/types";
import { PartCard } from "./part-card";

/** The bot asks you to pick. Once answered it shrinks to "✓ your choice". */
export function QuestionPart({ part, messageId }: { part: QuestionPartData; messageId: string }) {
  if (part.answered) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Check className="size-3.5 text-success" /> {part.question} <span className="font-medium text-foreground">{part.answered}</span>
      </p>
    );
  }

  return (
    <PartCard>
      <p className="mb-3 font-medium">{part.question}</p>
      <div className="flex flex-wrap gap-2">
        {part.options.map((option) => (
          <Button key={option} variant="outline" size="sm" onClick={() => actions.answerQuestion(messageId, option)}>
            {option}
          </Button>
        ))}
      </div>
    </PartCard>
  );
}
