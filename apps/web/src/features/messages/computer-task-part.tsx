import { toast } from "sonner";
import { Monitor } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { ComputerTaskPart as ComputerTaskPartData } from "@/data/types";
import { PartCard } from "./part-card";

const STATUS: Record<ComputerTaskPartData["status"], { label: string; className: string }> = {
  running: { label: "Working", className: "bg-working/15 text-working" },
  done: { label: "Done", className: "bg-success/15 text-success" },
  "needs-takeover": { label: "Needs you", className: "bg-brand/12 text-brand" },
  failed: { label: "Failed", className: "bg-destructive/12 text-destructive" },
};

/** Work the bot did on its own computer, with a way in when it needs a human to log in. */
export function ComputerTaskPart({ part }: { part: ComputerTaskPartData }) {
  const status = STATUS[part.status];

  return (
    <PartCard className="flex items-center gap-3">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-muted">
        <Monitor className="size-5 text-muted-foreground" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium">{part.title}</span>
        <span className="block text-xs text-muted-foreground">
          {part.app} · {part.stepCount} steps
        </span>
      </span>
      {part.status === "needs-takeover" ? (
        <Button size="sm" onClick={() => toast("Take over opens the bot's computer. Coming with the Computer view.")}>
          Take over
        </Button>
      ) : (
        <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-xs font-medium", status.className)}>{status.label}</span>
      )}
    </PartCard>
  );
}
