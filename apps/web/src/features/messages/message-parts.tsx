import type { Message } from "@/data/types";
import { ApprovalCard } from "@/features/approvals/approval-card";
import { ComputerTaskPart } from "./computer-task-part";
import { QuestionPart } from "./question-part";
import { ReasoningPart } from "./reasoning-part";
import { FilePart, HandoffPart, RoutineCreatedPart } from "./small-parts";
import { TextPart } from "./text-part";
import { WorkLogPart } from "./work-log-part";

/**
 * Turns each part of a message into its card. This switch is the one place that
 * knows every part type; TypeScript complains here if a new type is added and not handled.
 */
export function MessageParts({ message, isOwn }: { message: Message; isOwn: boolean }) {
  const isStreaming = message.status === "streaming";

  return message.parts.map((part, index) => {
    const key = `${message.id}-${index}`;
    switch (part.type) {
      case "text":
        return <TextPart key={key} part={part} isOwn={isOwn} isStreaming={isStreaming} />;
      case "reasoning":
        return <ReasoningPart key={key} part={part} />;
      case "work-log":
        return <WorkLogPart key={key} part={part} />;
      case "computer-task":
        return <ComputerTaskPart key={key} part={part} />;
      case "approval":
        return <ApprovalCard key={key} approvalId={part.approvalId} />;
      case "question":
        return <QuestionPart key={key} part={part} messageId={message.id} />;
      case "routine-created":
        return <RoutineCreatedPart key={key} part={part} />;
      case "file":
        return <FilePart key={key} part={part} />;
      case "handoff":
        return <HandoffPart key={key} part={part} />;
      default: {
        const unhandled: never = part;
        return unhandled;
      }
    }
  });
}
