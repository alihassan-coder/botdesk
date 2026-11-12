import { Check, Circle } from "lucide-react";
import type { WorkLogPart as WorkLogPartData } from "@/data/types";
import { PartCard } from "./part-card";

/** A checklist of what the bot did: "✓ Inbox → 12 threads labeled". */
export function WorkLogPart({ part }: { part: WorkLogPartData }) {
  return (
    <PartCard>
      <h3 className="mb-2 font-medium">{part.title}</h3>
      <ul className="flex flex-col gap-1.5">
        {part.items.map((item) => (
          <li key={item.label} className="flex items-start gap-2">
            {item.done ? (
              <Check className="mt-0.5 size-4 shrink-0 text-success" aria-label="Done" />
            ) : (
              <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-label="Not done yet" />
            )}
            <span>
              <span className="font-medium">{item.label}</span>
              {item.detail && <span className="text-muted-foreground"> → {item.detail}</span>}
            </span>
          </li>
        ))}
      </ul>
    </PartCard>
  );
}
